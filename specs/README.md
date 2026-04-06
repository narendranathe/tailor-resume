# tailor-resume — Architecture Decisions Journal

> Append-only. Never delete entries. Add new decisions with date headers.
> This is the canonical source of truth for **why** we built things the way we did.

---

## 2026-04-05 — v1 Foundations

### Context
Built a Claude Code skill (`tailor-resume`) to automate ATS-optimized resume generation.
Lives in two locations that stay in sync via `scripts/sync_global.py`:
- Work dir (tests/CI): `C:\tmp\tailor-resume-work\.claude\skills\tailor-resume\`
- Global (runtime): `~/.claude/skills/tailor-resume\`

### Architecture decisions

**Decision 1: Stdlib-only core**
All parsing, gap analysis, and LaTeX rendering use zero external dependencies.
Why: The skill must work offline, in CI, and on any machine without pip install.
Tradeoff: No semantic embeddings in core path — those live in optional extras.

**Decision 2: Dual-backend RAG (Pinecone + SQLite)**
`rag_store.py` uses Pinecone when `PINECONE_API_KEY` is set, otherwise SQLite at `~/.tailor_resume/profiles.db`.
Why: Zero-friction local dev; production-grade cloud for real use.
Pattern: `get_store()` factory hides the swap — callers never know which backend.

**Decision 3: MCP server as the Claude Code plugin boundary**
All Claude Code integration flows through `mcp_server.py` (4 tools: `extract_profile`, `analyze_gap`, `render_latex`, `run_pipeline`).
Why: The MCP protocol lets Claude call our pipeline as structured tools, not string prompts. This gives us typed inputs/outputs, error JSON, and auditability.

**Decision 4: No PII in templates**
`templates/resume_template.tex` has NO hardcoded name/email/phone.
All contact info flows through the `header` dict at render time.
Why: Multiple users can share one template. No accidental data leaks in git.

**Decision 5: STAR + 20-word hard limit enforced at render**
`star_validator.py` scores bullets (action verb + measurable result = STAR score 2/2).
`latex_renderer.truncate_to_limit()` physically cuts bullets at 20 words at render.
Why: Without enforcement, bullets creep long and break single-page layout. ATS parsers score non-compliant bullets lower.

**Decision 6: 4-component ATS formula**
`jd_gap_analyzer.estimate_ats_score()`:
```
40% keyword overlap + 30% category coverage + 20% bullet quality + 10% seniority signal
```
Why: Pure keyword overlap (1-component) misses format and depth signals. Four components correlate better with human recruiter scoring.
Source: Resume quality rubric in REFERENCE.md.

**Decision 7: `user_id` threaded through all layers**
`TailorConfig.user_id`, `TailorResult.user_id`, `GapReport.user_id`, `mcp_server.run_pipeline(user_id=...)`, SQLite index on `(user_id, stored_at DESC)`.
Why: Multi-tenancy must be designed in from the start. Retrofitting is expensive.
Default `user_id = ""` (empty string) = anonymous single-user mode — zero breaking change.

**Decision 8: Single-page always**
The renderer enforces single-page LaTeX. The iterative loop in SKILL.md has a max 3 passes, with the final pass compressing for page fit.
Why: Recruiters do not read page 2. Single-page also forces prioritization of the strongest evidence.

---

## 2026-04-05 — v2 PRD Decisions (recorded during PRD session)

### Scope decision: MVP enhancement vs SaaS bifurcation

**Decision: MVP enhances the CLI skill; PRD documents the full SaaS product vision.**
Why: Building a React/FastAPI SaaS is 10x the effort of enhancing the existing pipeline.
The skill already works — we add features that deliver immediate value (cover letter, GitHub ingestion, semantic scoring) without blocking on infra.
The PRD captures the full vision so future implementation has a blueprint, not just a backlog.

### ATS scoring: 3-option architecture

**Decision: Option C (Claude) primary → Option B (4-component hybrid) fallback → Option A (pure embedding cosine) toggle.**

- **Option C (Claude-as-judge)**: Send JD + resume to Claude with a structured scoring rubric. Claude returns JSON: `{score: int, reasoning: str, bullet_scores: [...], recommendations: [...]}`. Primary choice because Claude understands semantic alignment at a level no embedding distance metric captures.
- **Option B (4-component formula, current)**: Automatic fallback when Claude rate limit is hit, API key absent, or user opts out.
- **Option A (embedding cosine)**: User-selectable toggle ("Use semantic engine"). Embeds JD and resume via `text-embedding-3-small`, cosine similarity → ATS score. No Claude calls.

UI flow (when SaaS dashboard exists):
```
Score method toggle:
  [Claude AI ▼]  ←→  [Internal Engine]
                       ↓
            [JD + Resume only]  ←→  [Semantic (embeddings)]
```

When Claude is used: show side-by-side comparison (Claude score vs formula score) — user picks the better result or merges edits from both before downloading.

Fallback chain (automatic, no user action needed):
```
Claude API call → rate limit/error → Option B formula → always succeeds
```

Why this order: Option C gives the richest feedback; Option B is deterministic and free; Option A requires an embedding API key which may also be absent.

### GitHub vault for resume versioning

**Decision: One private GitHub repo (`narendranathe/resume-vault`), per-user branch, per-generation commit.**

Architecture:
```
resume-vault/
  └── Branch: vault/{user_id}/
        └── {Company}_{Role}_{YYYYMMDD_HHMMSS}.tex     ← LaTeX source
        └── {Company}_{Role}_{YYYYMMDD_HHMMSS}.pdf     ← compiled PDF (via GitHub Actions)
        └── {Company}_{Role}_{YYYYMMDD_HHMMSS}.meta.json ← ATS score, JD hash, generation method
```

**Git tag naming convention (inherited from autoapply-ai):**
`{FirstName}_{Company}_{Role}[_{JobID}]`
Example: `Narendranath_Google_SeniorDE_JOB12345`

Why per-user branch vs per-user folder on main:
- **Isolation**: No cross-user merge conflicts. Deleting a user's data = deleting the branch.
- **Audit trail**: `git log vault/{user_id}` shows complete history for that user only.
- **Compliance**: GDPR-style "right to erasure" is one branch delete.
- **Access control**: GitHub branch protection rules can restrict who can push to `vault/*` branches. Only the system account (owner: narendranathe) can push.

Rejected alternatives:
- **Separate repo per user**: Too many repos; GitHub free tier limits private repos.
- **Per-user folder on main**: Shared history makes deletion messy; merge conflicts possible.
- **Git LFS for PDFs**: Added complexity; PDFs compiled by CI Actions are small enough for regular storage.

**Ownership rules** (non-negotiable):
- The `resume-vault` repo is owned exclusively by narendranathe.
- Users never have direct GitHub access. All reads/writes go through the API layer.
- Users can download their resumes but cannot push/pull to the vault directly.
- User data deletion: branch delete + DB purge. No user-initiated deletion (support ticket required).

**Versioning rules (from autoapply-ai):**
- `version_tag`: `{FirstName}_{Company}_{Role}[_{JobID}]` — internal git tag
- `recruiter_filename`: Always `{FirstName}.pdf` at download time — never expose internal tags to recruiters
- `file_hash`: SHA-256 of raw file bytes — skip re-uploading identical files
- `is_base_template`: True for the master resume; False for all tailored variants
- `is_generated`: True when LLM-produced

### Billing and pricing

**Competitive benchmark (2026-04):**
| Product | Free | Starter | Pro | Notes |
|---------|------|---------|-----|-------|
| Jobright.ai | Limited | ~$19.99/mo | - | AI job matching + resume |
| Simplify.com | 10/mo | ~$12/mo | ~$30/mo | Resume + autofill |
| Kickresume | 1 resume | ~$10/mo | - | Templates only |
| Resume.io | - | ~$8/mo | - | No ATS scoring |

**Pricing target: 50% cheaper than mid-market ($15/mo average) = $7.50/mo Pro.**

**Token cost calculation (Claude Sonnet 4.6 @ $3/MTok input, $15/MTok output):**
Per resume generation (full pipeline with Claude scoring):
- Profile extraction: ~2k tokens in
- JD analysis: ~3k tokens in
- Claude ATS scoring: ~6k tokens in, ~1.5k tokens out
- Cover letter (if requested): ~4k in, ~2k out
- Total per resume: ~15k in, ~3.5k out
- Cost: (15k × $3 + 3.5k × $15) / 1,000,000 = $0.045 + $0.053 = **~$0.10/resume**

**Tier design (5x token cost markup):**

| Tier | Price | Daily limit | Monthly token cost basis | 5x markup |
|------|-------|-------------|--------------------------|-----------|
| Free | $0 | 3/day | 3 × $0.10 × 30 = $9 | absorbed as CAC |
| Starter | $4.99/mo | 15/day | 15 × $0.10 × 30 = $45 → real users avg 5/day = $15/mo | 5× = $75 → cap at $4.99 for acquisition |
| Pro | $9.99/mo | 50/day | avg 20/day × $0.10 × 30 = $60/mo | 5× exceeds → price for P50 user: 10/day avg → $30 × 5× = ~$9.99 |
| Unlimited | $29.99/mo | 200/day rate limit | P90 user 50/day × $0.10 × 30 = $150 | 5× = $750 → not viable at flat rate; use rate limit + fair-use cap |
| API/Team | $99/mo | 1000/day rate limit | 1000 × $0.10 × 30 = $3,000 token cost/mo | Not viable solo — activate only with Narendra approval; priced for B2B |

**Note on Unlimited tier**: The 1000 resumes/day limit specified is a rate limit ceiling, not the expected average. Price Unlimited at P90 user behavior ($29.99), enforce the ceiling as anti-abuse protection, not as a typical usage cap.

**Anti-bot and abuse protection:**
- Rate limits enforced per `user_id` + IP via Redis sliding window
- Pattern detection: >20 resumes in 60 minutes after midnight local time = bot flag
- Warning sequence: warn × 4 → 24-hour deactivation → repeat 5 times → permanent block
- Counter shown to user on each warning: "This looks like bot activity. Warning 2/4. Account will be deactivated for 24 hours if this continues."
- Appeals via support ticket (admin resolves within 24h)

### Cover letter output

**Decision: Support .tex (source), .pdf (compiled), .txt (plain), .docx (via python-docx).**

Format preference: User selects at download time; .pdf is default.
Why .txt in addition: Most job portals don't accept file uploads — they have text boxes. Copy-paste from .txt is the primary use case.

**Content structure (2 paragraphs, max 250 words total):**
- Para 1: Hook — why this role + company (pull from JD signals: mission, product, team context)
- Para 2: Impact — 2-3 specific achievements from the resume that map to top JD requirements (STAR-compressed, no bullet points)

Tone: Confident, specific, not sycophantic. No "I am writing to express my interest in..." openers.

**Visual design**: Matches resume header (same contact block, same font). LaTeX source shares font/color definitions with `resume_template.tex`.

### resume-rules submodule

**Decision: Submodule contains docs + scripts. Contributors: Narendra + validated open-source contributors.**

Submodule repo: `narendranathe/resume-rules`
Contents:
- `SKILL.md`, `REFERENCE.md`, `EXAMPLES.md` — the scoring rubric and bullet standards
- `scripts/star_validator.py`, `scripts/text_utils.py` — stateless validators with no I/O side effects

Contribution process:
1. PR to `resume-rules` repo
2. Narendra reviews and approves
3. After approval, update submodule pointer in `tailor-resume` and sync global

Why submodule vs copy: Rules evolve. If the STAR rubric tightens (e.g., 18-word limit), one commit propagates to all projects that use the submodule.

### Internal tool first, SaaS later

**Decision: v2 MVP = browser UI for Narendra's own use. v3 = B2B/B2C SaaS.**

Why this order:
- Dog-fooding before customer-facing: If the tool isn't good enough for Narendra to use daily, it's not ready for paying customers.
- Avoids premature infra cost: Clerk auth, Supabase, Fly.io, Stripe add monthly fixed costs before product-market fit.
- Validates UX assumptions: What friction points exist when using it from a browser vs CLI?

Migration path: The FastAPI backend is designed as the API layer for both the internal tool and the future SaaS. No rewrite needed — just add public auth (Clerk) and billing (Stripe) routes to the same backend.

---

## Open decisions (to be resolved in implementation)

- [ ] GitHub Actions workflow for auto-compiling .tex → .pdf in resume-vault (on each push to `vault/*` branches)
- [ ] Rate limit backend: Redis (Upstash) or in-memory per-process for MVP internal tool?
- [ ] DOCX generation library: `python-docx` vs `pandoc` subprocess — python-docx already wired; pandoc not pursued
- [x] GitHub ingestion: PAT (`GITHUB_TOKEN` env) for private repos; public repos require no token (60 req/hr)
- [ ] Admin ticketing: Linear integration vs custom SQLite ticket table for MVP
- [ ] Anti-bot detection: rule-based (rate + time-of-day) for MVP vs ML anomaly detection for v3
- [ ] resume-rules submodule: CI updated (`submodules: recursive`); manual step pending — create `narendranathe/resume-rules` repo, then `git submodule add https://github.com/narendranathe/resume-rules resume-rules`

---

## 2026-04-05 — v2 Wave 1: API Server + ATS Facade + Cover Letter (commits 5a34f5b → 39f9aa6)

### Issue #61 — FastAPI browser UI (`api_server.py`)

**Decision: Localhost FastAPI server replacing CLI for day-to-day use.**

Architecture:
```
GET  /          → serves templates/ui/index.html (vanilla HTML/CSS, no JS framework)
GET  /health    → {"status": "ok", "version": "2.0.0"}
POST /generate  → full pipeline: artifact + JD → ATS score + resume.tex
POST /score     → JD + resume text → ATS score + gap_report
```

Auth: `X-API-Key` header checked against `API_KEY` env var (default: `"dev-key"`).
Why single shared key: MVP internal tool — no multi-user auth needed until SaaS phase.

**Decision: Vanilla HTML/CSS UI (no React, no Vite).**
Why: Zero build toolchain for an internal dev tool. Server starts with `python api_server.py` — no `npm install`, no bundler, no node_modules. React/Vite will be added when the public SaaS UI phase begins.

### Issue #62 — Unified ATS scoring facade (`ats_scorer.py`)

**Decision: `score(jd, resume, method="formula")` as the single entry point for all three engines.**

```python
score(jd, resume, method="formula")    # Option B — 4-component, zero deps
score(jd, resume, method="embedding")  # Option A — cosine similarity via embed()
score(jd, resume, method="claude")     # Option C — Claude-as-judge (stub → implemented in #63)
compare(jd, resume)                    # returns (formula_result, claude_result) side-by-side
```

All three engines return `ATSScoreResult(score, reasoning, bullet_scores, recommendations, method_used, formula_score)`.

`formula_score` field: embedding and claude results always populate this too (via a secondary `run_analysis()` call), so the UI can always show the formula baseline for comparison.

**Decision: `method="embedding"` falls back to TF-IDF 128-dim when `OPENAI_API_KEY` is absent.**
Why: The embedding engine should never hard-fail. TF-IDF character n-gram cosine is a reasonable offline approximation. The fallback label includes `(tfidf fallback)` so callers can distinguish.

### Issue #64 — Cover letter renderer (`cover_letter_renderer.py`)

**Decision: Two-method design — `method="template"` (deterministic, zero deps) and `method="claude"` (LLM, lazy import, falls back to template).**

Why `method="template"` as default in API: API calls should be fast and deterministic. Claude method is opt-in via `method` field in the request.

**Decision: `_enforce_word_limit(para1, para2, 250)` trims at sentence boundary, not mid-word.**
The combined 2-paragraph text is trimmed to ≤250 words by walking back from the word limit to the nearest `.`, `!`, or `?`. This preserves grammatical completeness even when truncating.

**Decision: DOCX written to `tempfile.NamedTemporaryFile` and path returned; caller owns cleanup.**
Why: The server doesn't know if the caller wants to persist the docx. Returning the temp path lets the caller copy/move it as needed. File is silently skipped if `python-docx` is not installed.

**Decision: LaTeX cover letter shares font/margin definitions with `resume_template.tex`.**
The cover letter header uses identical `\fontsize`, `\geometry`, and color macros so resume + cover letter render as a matched pair in Overleaf/pdflatex.

---

## 2026-04-05 — v2 Wave 2: Vault + GitHub Ingestion + CI (commits 39f9aa6 → 743ad71)

### Issue #65 — GitHub vault client (`vault_client.py`)

**Decision: stdlib `urllib` only — no `httpx`, no `requests`.**
Why: `vault_client.py` must work in the same zero-dep environment as the core pipeline. `httpx` is in `requirements-optional.txt` but cannot be assumed present.
Tradeoff: No async, no connection pooling. Acceptable for a CI/CD-time operation (vault push is non-blocking from the caller's perspective).

**Decision: Non-blocking push — `push_version()` returns `None` silently when token is absent.**
Why: Vault versioning is an enhancement, not a requirement. If `GITHUB_VAULT_TOKEN` is not set (e.g., local dev, CI without secrets), the pipeline continues without error. Callers check for `None` but never crash on it.

**Decision: `.tex` + `.meta.json` committed as two separate API calls, not a tree commit.**
Why: Two sequential `PUT /contents/{path}` calls are simpler than building a Git tree object. The small latency cost (two API roundtrips vs one) is acceptable for an async background operation.

**Decision: `_file_sha()` pre-fetch before every PUT.**
GitHub's Contents API requires the blob SHA to update an existing file. We fetch it first and include it in the PUT body if the file exists. If it doesn't exist, we skip the `sha` field. This handles re-generation of the same resume without conflict errors.

### Issue #66 — GitHub repo ingester (`github_ingester.py`)

**Decision: `fetch_user_repos()` skips forks by default (`include_forks=False`).**
Why: Forks are not original work. ATS-optimized resumes must show owned, original projects. The option exists for power users who want to include significant fork contributions.

**Decision: `_fetch_readme()` extracts only the first 3 non-trivial bullet lines (>15 chars).**
Why: Full README text would overwhelm the profile with noise. Three bullets is enough to capture the "features" or "what this does" section. `_README_MAX_CHARS = 2000` caps the raw download size.

**Decision: Repos with ≥10 stars get a star bullet injected automatically.**
Why: Star count is a proxy for community validation — a legitimate ATS signal. 10 is the threshold because below that it's likely just the author and friends.

**Decision: `inject_github_projects()` deduplicates by name (case-insensitive) and lets existing profile entries win.**
Why: If the user has already written a polished project description in their blob/LinkedIn import, that must not be overwritten by a raw GitHub description. The ingester enriches, it doesn't replace.

### Issue #68 — CI submodule support

**Decision: Add `submodules: recursive` to `actions/checkout@v4` in `ci.yml`.**
Why: When `resume-rules` submodule is eventually wired, CI must check it out alongside the main repo. Adding it now costs nothing and prevents a future CI break.

Status: `ci.yml` updated. The actual submodule `.gitmodules` wiring is a manual step (requires the `narendranathe/resume-rules` repo to exist first).

---

## 2026-04-05 — v2 Wave 3: Claude Scorer + Full API Integration (commits 743ad71 → 19a9d41)

### Issue #63 — Claude-as-judge ATS scorer (Option C)

**Decision: Use `claude-haiku-4-5-20251001` (not Sonnet) for ATS scoring.**
Why: Haiku is 5x cheaper than Sonnet and ATS scoring is a structured JSON extraction task — not a reasoning-heavy task. The scoring rubric is explicit; the model just needs to apply it. If scoring quality regresses, upgrading to Sonnet is one string change.

**Decision: Silent fallback to formula on ANY exception (import error, rate limit, parse failure, quota).**
The fallback result sets `method_used = "claude (formula fallback)"` so the UI can show a downgrade notice if desired, but the pipeline never crashes.

**Decision: Score clamped to [0, 100] regardless of Claude's output.**
Claude occasionally returns scores like 102 or -5 when miscalibrated. Hard clamp at runtime is safer than trusting model output range.

**Decision: Claude result always includes `formula_score` field (secondary `run_analysis()` call).**
Why: Side-by-side comparison requires both numbers. The `/compare` endpoint and the browser UI ATS panel both display `(Claude: 82, Formula: 71)` — users can eyeball which to trust.

**Prompt engineering decision: Single-turn JSON extraction prompt.**
```
"Return ONLY valid JSON — no prose, no fences — with exactly these keys:
 {"score": int, "reasoning": str, "bullet_scores": [...], "recommendations": [...]}"
```
Why single-turn: Tool-use / structured output would require a tool schema; keeping it as a raw JSON prompt is simpler and works across all Claude models without API changes. Fence stripping with regex handles occasional markdown-wrapped responses.

**`compare()` signature change:**
Old: `compare()` raised `NotImplementedError` (Claude was a stub).
New: `compare()` returns `(formula_result, claude_result)`. Formula is always first (deterministic, always succeeds). Claude result may be a fallback — caller can check `method_used`.

### Issue #67 — Full api_server integration

**Decision: Three new endpoints wired to the modules built in Waves 1-2.**

```
POST /cover-letter   → cover_letter_renderer.build_cover_letter()
POST /ingest/github  → github_ingester.fetch_user_repos()
POST /generate       → (existing) + push_version() vault push (non-blocking)
```

**Decision: `POST /generate` vault push is fire-and-forget inside a bare `try/except`.**
The vault push reads the `.tex` file written by `execute_text()`, then calls `push_version()`. If this fails for any reason (token missing, network, file not found), the exception is swallowed and `vault_version: null` is returned. The resume is already generated — vault is an enhancement.

**Decision: company name in vault push is extracted as `jd_text.split()[0][:30]`.**
This is intentionally rough. For MVP internal tool, the first word of the JD is usually the company name. A proper company extractor (like in `cover_letter_renderer._extract_company_from_jd()`) will be wired in a follow-up — tracked in open decisions.

**Decision: `POST /cover-letter` uses `dataclasses.asdict()` to convert Profile to a plain dict.**
`cover_letter_renderer` expects dict inputs (for duck-typing compatibility with JSON profiles from `pipeline.execute_text`). `profile_extractor` returns typed dataclasses. `dataclasses.asdict()` is the correct bridge — it recursively serializes nested dataclasses (Role, Bullet, etc.) to plain dicts.

**Decision: `POST /ingest/github` defaults `fetch_readmes=False`.**
README fetching requires one extra HTTP call per repo. In an API context where the user might be requesting 10-20 repos synchronously, this adds 10-20 serial network calls. Disabled by default; opt-in via `fetch_readmes: true` in the request body.

---

## Coverage and quality gates (as of 2026-04-05)

| Metric | Value | Gate |
|--------|-------|------|
| Tests | 310 passing, 1 skipped | - |
| Coverage | 80.4% total | ≥80% required |
| Lint | Clean (ruff) | CI enforced |
| Scripts | 16 modules | - |
| Test files | 16 test files | - |

### Coverage gaps (not blocking, known acceptable misses)
- `cli.py` — 0%: CLI entry point; excluded from coverage concern (tested via integration, not unit)
- `pipeline.py` — 61%: The async RAG store paths and Pinecone backend are skipped in unit tests (require live API keys)
- `rag_store.py` — 67%: Same reason — Pinecone and SQLite persistence paths tested only in integration
- `github_ingester.py` — 69%: CLI `__main__` block and HTTP error-path branches not covered by unit tests

### Open decisions (to be resolved in next wave)

- [x] Company name extraction in vault push: fixed — `_extract_company_from_jd()` now used
- [x] `/generate` user_id field: added, threads to push_version (priority: user_id > email > anonymous)
- [x] Browser UI Cover Letter tab: implemented
- [x] Browser UI GitHub Projects tab: implemented
- [x] `/compare` endpoint: implemented
- [ ] PDF compilation: `pdflatex` subprocess in `/generate` when on PATH; return `pdf_path`
- [ ] Vault PDF: GitHub Actions workflow on `vault/*` branches to compile `.tex` → `.pdf`

---

## 2026-04-05 — v2 Wave 4: /compare endpoint + UI tabs + quality fixes (60d2a07)

### Hooks audit (performed this session)

Active Claude Code hooks verified:
| Hook | Trigger | Action | Status |
|------|---------|--------|--------|
| `sync_skills.py` | PostToolUse Edit\|Write | Auto-syncs `.claude/skills/<name>/` to `~/.claude/skills/<name>/` | Working |
| `block-dangerous-git.sh` | PreToolUse Bash | Blocks force-push, rm -rf root, reset --hard | Active |
| `pre-action-gate.sh` | PreToolUse all | Checks gates.json for block/warn patterns | Active — 6 gates |
| `session-start.sh` | SessionStart | Loads primer.md into context | Active |
| `session-end.sh` | SessionEnd | Rewrites primer.md with session summary; promotes repeated failures to gates | Active |
| `post-compact.sh` | PostCompact | (runs after context compaction) | Active |

Gates active: `no-force-push` (block), `no-rm-rf-root` (block), `no-credentials-in-files` (block), `no-git-reset-hard` (warn), `no-drop-database` (block), `no-delete-migrations` (warn). No auto-promoted failures in `failures.json`.

### Issue: /compare endpoint

**Decision: `/compare` reuses the existing `ScoreRequest` model (jd_text + resume_text).**
Why: The compare operation scores the same inputs with two engines — no new fields needed. Sharing the model avoids a proliferating family of near-identical Pydantic classes.

**Response shape:**
```json
{
  "formula": {"score": 71, "method_used": "formula", "reasoning": "...", "recommendations": [...]},
  "claude":  {"score": 82, "method_used": "claude", "reasoning": "...", "recommendations": [...],
              "bullet_scores": [...], "formula_score": 71}
}
```
The `claude.formula_score` field is the formula result embedded in the Claude ATSScoreResult — so the UI can always show the baseline without making two separate requests.

### Issue: Vault push company extraction fix

**Decision: Replaced `jd_text.split()[0][:30]` with `_extract_company_from_jd(jd_text)` from `cover_letter_renderer`.**
Why: The rough `split()[0]` approach returned words like "Senior" or "We" when the JD starts with a seniority level or intro phrase. `_extract_company_from_jd()` uses regex patterns to find company names after "at", "join", or at line start followed by "is hiring/looking/seeking".

**Decision: `user_id` priority chain: `req.user_id > req.email > "anonymous"`.**
This lets callers pass an explicit opaque user ID (e.g., a Clerk user ID from autoapply-ai) without coupling to email. Email remains the fallback for simple internal tool usage where no auth system exists.

### Issue: Browser UI tab navigation

**Decision: Four tabs — Resume, Cover Letter, ATS Compare, GitHub Projects — all sharing the top Inputs card.**
Why shared inputs: JD text and resume artifact are common to all operations. Duplicating them in each tab would create sync issues if the user edits one copy. Single source of truth at the top; tabs switch the action, not the inputs.

**Decision: `escHtml()` utility in JS for all user-facing dynamic content.**
Why: The result area renders untrusted content from the API (JD text, reasoning strings, project descriptions). All dynamic content is escaped to prevent accidental XSS from special characters in resume text.

**Decision: GitHub Projects tab defaults `fetch_readmes=false`.**
Already captured in Wave 3 decisions. UI exposes it as an opt-in checkbox with "(slower)" label so users understand the tradeoff.

**Decision: Cover Letter "Copy plain text" button uses `navigator.clipboard.writeText()`.**
Why: The most common use case is copy-paste into a job portal text box. A dedicated copy button eliminates the need to select-all in the text area. Shows "Copied!" for 1.5s then resets — standard UX pattern.
