# PRD: Web Routes Sprint — Artifact Format, Rate Limiting, DOCX Output

## Problem

Three bugs compound to make the POST `/resume/tailor` endpoint unreliable for any binary resume upload and unprotected against abuse. First, `routes/resume.py` constructs `TailorConfig(artifacts=[tmp_path])` — a list of bare strings — while `pipeline.py` defines `artifacts: List[Tuple[str, str]]` (each element must be `(file_path, format_name)`); this causes an immediate `ValueError` on every PDF or DOCX upload as `execute()` tries to unpack the string into `(path, fmt)`. Second, neither upload handler enforces a file-size cap or per-IP request rate, so a malicious caller can exhaust server memory with a giant file or drain free-tier quota via rapid-fire requests with no friction. Third, the endpoint returns only `tex_b64`, giving the frontend no path to serve a DOCX download — a capability users expect given the DOCX parser that already exists. Left unfixed: binary resume uploads always 422, the server is open to trivial DoS/quota-draining attacks, and the frontend cannot offer DOCX export without a separate, uncached pipeline run.

## Users

| Persona | Resume source / entry point | Impact |
|---|---|---|
| Job seeker (free tier) | Uploads PDF/DOCX resume via React frontend | Every binary upload 422s; never gets a tailored resume |
| Job seeker (pro tier) | Uses API directly with large DOCX files | No file-size guard; can accidentally upload multi-hundred-MB files |
| Malicious actor | Scripted POST loop against `/resume/tailor` | Can drain another user's free-tier quota or overwhelm the server without rate limits |
| Frontend developer | Consumes `/resume/tailor` JSON response | `docx_b64` field absent; must build a separate download flow or omit DOCX output |

## User Stories

1. As a job seeker, I want to upload my PDF resume and receive a tailored `.tex` output, so that I don't get a 422 error just because my file is binary.
2. As a free-tier user, I want the server to reject requests that exceed the rate limit with a clear 429 response, so that my monthly quota is not drained by a replay attack.
3. As a frontend developer, I want the `/resume/tailor` response to include `docx_b64` alongside `tex_b64`, so that I can offer users a one-click DOCX download without a second API round-trip.

## Flow

```
BEFORE (broken path for binary uploads):
  POST /resume/tailor (PDF/DOCX)
        |
        v
  _run_pipeline()
        |
        v
  TailorConfig(artifacts=["/tmp/abc.pdf"])   ← bare string, not tuple
        |
        v
  execute(cfg)
        |
        v
  for path, fmt in config.artifacts:         ← ValueError: too many values to unpack
        |
        v
  HTTP 422  (user sees "Pipeline error")

AFTER (fixed path):
  POST /resume/tailor (any format)
        |
        v
  File-size check (> 10 MB → 413)
        |
        v
  Rate-limit check (> 10/min per IP → 429)
        |
        v
  _run_pipeline()
        |
        v
  TailorConfig(artifacts=[("/tmp/abc.pdf", "pdf")])   ← correct tuple
        |
        v
  execute(cfg)  — template existence checked first
        |
        v
  TailorResult  → tex_b64 + docx_b64 both populated
        |
        v
  HTTP 200  { ats_score, gap_summary, report, tex_b64, docx_b64 }
```

## Modules

| File | Line range | Exact change description |
|---|---|---|
| `web_app/backend/app/routes/resume.py` | 132 | Fix `TailorConfig(artifacts=[tmp_path])` → `artifacts=[(tmp_path, detected_format)]`; add `MAX_UPLOAD_BYTES` + file-size guard; add in-memory rate limiter (`_check_rate`); add `docx_b64` field population in response |
| `web_app/backend/app/routes/resume.py` | 30–35 | Add `docx_b64: Optional[str] = None` field to `TailorResponse` |
| `web_app/backend/app/routes/profile.py` | 59–60 | Add `MAX_UPLOAD_BYTES` file-size guard before parsing binary artifact |
| `.claude/skills/tailor-resume/scripts/pipeline.py` | 82–95 | Add template existence pre-check in `execute()` before iterating artifacts |

## Acceptance Criteria

- [ ] `POST /resume/tailor` with a PDF upload returns HTTP 200 (not 422) — the tuple-format fix routes the artifact through `execute()` without a `ValueError`.
- [ ] `POST /resume/tailor` with a file larger than 10 MB returns HTTP 413 with detail `"File too large. Max size: 10 MB."`.
- [ ] After 10 requests from the same IP within 60 seconds, the 11th `POST /resume/tailor` returns HTTP 429 with detail `"Rate limit exceeded"`.
- [ ] `POST /resume/tailor` response JSON includes `docx_b64` key (may be `null` when DOCX renderer is unavailable, must be present in the schema).
- [ ] `POST /profile` with a file larger than 10 MB returns HTTP 413.
- [ ] `pipeline.execute()` raises `FileNotFoundError` with a human-readable message when `template_path` does not exist, instead of a `KeyError` or `FileNotFoundError` with no context.

## Metrics

| Metric | Before | After |
|---|---|---|
| Binary upload success rate (PDF/DOCX) | 0% (always 422) | 100% for valid files ≤ 10 MB |
| Max upload size enforced | None | 10 MB (HTTP 413) |
| Rate limit enforced | None | 10 req/min per IP (HTTP 429) |
| Response fields for DOCX | Not present | `docx_b64` field always present in schema |
| Pipeline template error clarity | `KeyError` or cryptic `FileNotFoundError` | `FileNotFoundError: Template not found: <path>` |
| Passing tests (test_web_api + test_billing) | Baseline | All pre-existing tests green + new guards tested |
