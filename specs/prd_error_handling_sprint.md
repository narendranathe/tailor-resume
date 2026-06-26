# PRD: Error Handling Sprint — Silent Exception Suppression

## Problem

Two modules swallow exceptions silently: `cover_letter_renderer.py` catches every exception in
`_build_claude()` with a bare `except Exception:` and discards both the error and any diagnostic
context, making it impossible to distinguish a transient rate-limit hit (recoverable, should
surface a warning) from a hard coding bug (should alert an engineer). In `billing.py`,
`_revert_plan_by_customer()` wraps its Supabase update in a bare `except Exception: pass`,
silently returning without reverting the user's plan to `free` on subscription cancellation; worse,
the outer webhook handler still returns HTTP 200 to Stripe, so Stripe marks the event as
successfully delivered and never retries it. The combined effect is: (1) Claude cover-letter
failures are invisible — support cannot tell how often LLM calls fail or why; (2) users who cancel
their Pro subscription may retain Pro access indefinitely because the plan revert was silently
dropped; and (3) no structured logs exist to trigger alerts or drive SLA monitoring. Left unfixed,
this creates both a revenue-integrity risk (free rides for cancelled subscribers) and an
observability black hole that makes production incidents undetectable.

## Users

| Persona | Resume source / entry point | Impact |
|---|---|---|
| Free-tier job seeker | Web UI → `POST /resume/tailor` with cover letter | Cover-letter generation silently falls back to template with no user-facing explanation; may appear broken |
| Pro subscriber (active) | Web UI checkout → Stripe Pro subscription | Unaffected by billing bug; may experience undisclosed Claude failures |
| Cancelled Pro subscriber | Stripe cancellation → webhook `customer.subscription.deleted` | Plan may never revert to free; user retains Pro perks without paying |
| Platform engineer / on-call | Datadog / CloudWatch log tail | No actionable log lines on LLM failure or billing event failure; SLO monitoring blind |

## User Stories

1. **As a platform engineer**, I want every Claude API failure during cover-letter generation to emit
   a structured `logger.exception` line with the customer id and exception detail, so that I can
   set a log-based alert and know within minutes when the LLM call degradation rate exceeds 1%.

2. **As the product owner**, I want a cancelled Stripe subscriber's plan to revert to `free` on the
   same webhook delivery, or for Stripe to retry the webhook if the Supabase call fails, so that
   no cancelled user retains Pro benefits beyond the retry window.

3. **As a free-tier user**, I want to be able to see a clear fallback (template cover letter) when
   Claude is unavailable, with the `method_used` field set to `"template (claude fallback)"`,
   so that I know the output is rule-based and can adjust my expectations.

## Flow

```
BEFORE (cover letter)
  _build_claude()
    try:
      anthropic call ──► success → assemble
    except Exception:   ← catches EVERYTHING silently
      _build_template() ← no log, no rate-limit distinction

AFTER (cover letter)
  _build_claude()
    try:
      anthropic call ──► success → assemble
    except anthropic.RateLimitError as exc:
      logger.warning(...)  ← distinguishable, operator-visible
      _build_template()
    except Exception as exc:
      logger.exception(...)  ← stack trace in logs
      _build_template()

BEFORE (billing webhook)
  stripe_webhook()
    event = checkout.session.completed / subscription.deleted
    _revert_plan_by_customer(cid)
      try:
        supabase update ──► Exception:
          pass  ← silent swallow; caller returns HTTP 200
  return {"received": True}  ← Stripe marks as delivered; never retries

AFTER (billing webhook)
  stripe_webhook()
    event = customer.subscription.deleted
    _revert_plan_by_customer(cid)  ← may raise HTTPException(500)
      try:
        supabase update ──► success → set_user_plan("free")
      except Exception as exc:
        logger.exception(...)
        raise HTTPException(500, ...)  ← propagates up
    ← HTTPException(500) propagates → Stripe receives 500 → retries
```

## Modules

| File | Line range | Exact change description |
|---|---|---|
| `.claude/skills/tailor-resume/scripts/cover_letter_renderer.py` | 19–27 (imports) | Add `import logging` and `logger = logging.getLogger(__name__)` at module level |
| `.claude/skills/tailor-resume/scripts/cover_letter_renderer.py` | 127–135 | Replace bare `except Exception:` with two handlers: `except anthropic.RateLimitError as exc` (logger.warning + fallback) and `except Exception as exc` (logger.exception + fallback) |
| `.claude/skills/tailor-resume/scripts/cover_letter_renderer.py` | 315–316 | Replace silent `except Exception: docx_path = None` with logged warning via `logger.warning` |
| `web_app/backend/app/routes/billing.py` | 1–17 (imports) | Add `import logging` and `logger = logging.getLogger(__name__)` at module level |
| `web_app/backend/app/routes/billing.py` | 155–185 | Replace Supabase `except Exception: pass` in `_revert_plan_by_customer()` with `logger.exception(...)` + `raise HTTPException(status_code=500, ...)` |
| `web_app/backend/app/routes/billing.py` | 143–152 | Add `logger.exception` to any remaining silent except blocks inside the webhook handler |

## Acceptance Criteria

- [ ] `_build_claude()` bare `except Exception:` is replaced; running with a mocked
      `anthropic.RateLimitError` emits a `WARNING`-level log line containing the customer context
      and falls back to template method, returning `method_used="template (claude fallback)"`.
- [ ] `_build_claude()` non-rate-limit exception (e.g., `ValueError`) emits an `ERROR`-level log
      line (via `logger.exception`) including the full stack trace and falls back to template.
- [ ] `_revert_plan_by_customer()` Supabase failure raises `HTTPException(status_code=500)` rather
      than returning silently, causing the webhook endpoint to respond with HTTP 500 so Stripe will
      retry the event.
- [ ] All modified `except` blocks emit at minimum a `logger.warning` or `logger.exception` call;
      no `pass` or silent swallow remains in the two owned files.
- [ ] Existing `tests/test_billing.py` suite passes without modification (all 10 tests green or
      skipped due to missing web deps, zero new failures).

## Metrics

| Metric | Before | After |
|---|---|---|
| Silent exception swallows (owned files) | 3 (cover_letter × 2, billing × 1) | 0 |
| Log lines emitted on Claude rate-limit hit | 0 | 1 WARNING per occurrence |
| Log lines emitted on hard Claude failure | 0 | 1 ERROR + stack trace per occurrence |
| Stripe retry on Supabase plan-revert failure | Never (HTTP 200 returned) | Always (HTTP 500 triggers Stripe retry) |
| test_billing.py pass count | 10 pass / 0 fail (or all skip) | 10 pass / 0 fail (or all skip) |
| Bare `except` blocks in owned files | 3 | 0 |
