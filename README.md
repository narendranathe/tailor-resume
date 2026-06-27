# tailor-resume

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://tailor-resume-ai.streamlit.app/)
[![CI](https://github.com/narendranathe/tailor-resume/actions/workflows/ci.yml/badge.svg)](https://github.com/narendranathe/tailor-resume/actions/workflows/ci.yml)

Paste a job description and your work history. Get a tailored single-page LaTeX resume with quantified bullets, ATS score, and gap analysis — in minutes. No fabrication. No templates with your name baked in. No API keys required for the core pipeline.

---

## What it does

tailor-resume is an ATS-optimized resume tailoring pipeline powered by Claude Code. It parses your work history from any format — blobs, PDFs, Markdown, LinkedIn exports, GitHub repos — scores it against a job description using a 4-component ATS formula, identifies the exact signals you're missing, and renders a recruiter-ready single-page LaTeX resume with rewritten, metric-dense bullets. The result is a `.tex` file you compile locally or upload to Overleaf.

The pipeline is entirely deterministic: the same inputs always produce the same output. No AI hallucination, no invented metrics, no PII hardcoded anywhere.

---

## How to use it — three paths

### Fastest: Browser (no install)

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://tailor-resume-ai.streamlit.app/)

Open the Streamlit app, paste your resume and a job description, download `resume_tailored.tex`, upload to Overleaf.

### Interactive: Claude Code skill

```
/tailor-resume
```

Claude asks for your JD and work history, runs gap analysis, rewrites bullets in three passes, and produces `resume.tex`. Works from any project once installed globally.

### Programmatic: Python API or CLI

```bash
# One command
python .claude/skills/tailor-resume/scripts/cli.py \
  --jd fixtures/sample_jd.txt \
  --artifact fixtures/sample_blob.txt:blob \
  --name "Jane Smith" --email "jane@example.com" \
  --output out/resume.tex
```

```python
from tailor_resume import run_pipeline
result = run_pipeline(jd_text=open("jd.txt").read(), artifact_text=open("resume.md").read())
print(f"ATS: {result['ats_score']}/100 -> {result['output_path']}")
```

---

## Project Status

### Tier 1 — Zero infrastructure

| Feature | Status | Notes |
|---------|--------|-------|
| Core pipeline (parse → gap → render) | ✅ Done | stdlib only, 458+ tests |
| Claude Code skill (`/tailor-resume`) | ✅ Done | per-project + global install |
| MCP plugin (4 typed tools) | ✅ Done | stdio, auto-registered |
| ATS Relevance Gate (score bands + honest ceiling) | ✅ Done | ≥80→97+, 60-79→90+, <50→decline |
| `make install-global` | ✅ Done | one-command global install |
| Auto-invoke from natural language | ✅ Done | CLAUDE.md hook |
| **Streamlit web app** (3-tab browser UI) | ✅ Done | profile→tailor→download + SQLite save/load |
| **PyPI package** (`pip install tailor-resume`) | ✅ Done | `pyproject.toml` + Python API |
| **Docker image** | 📋 [#33](https://github.com/narendranathe/tailor-resume/issues/33) | bundles Python + pdflatex + deps |
| Streamlit Community Cloud deploy | ✅ Live | https://tailor-resume-ai.streamlit.app/ |
| Fly.io MCP deploy | 📋 Pending | needs `FLY_API_TOKEN` secret in GitHub |
| PyPI publish | 📋 Pending | configure trusted publisher, push `v0.1.0` tag |

### Tier 2 — Hosted web app

| Feature | Status | Notes |
|---------|--------|-------|
| **Hosted MCP server** (HTTP/SSE, Fly.io) | ✅ Done | server.py + Dockerfile + fly.toml + CI deploy |
| **FastAPI backend** (`/tailor` + `/profile` + `/health`) | 📋 [#34](https://github.com/narendranathe/tailor-resume/issues/34) | Clerk auth · Fly.io |
| **React web app** (gap chart + ATS score + download) | 📋 [#35](https://github.com/narendranathe/tailor-resume/issues/35) | Vite + Recharts · Vercel deploy |

### Tier 3 — Integrations

| Feature | Status | Notes |
|---------|--------|-------|
| **autoapply-ai integration** | 📋 [#36](https://github.com/narendranathe/tailor-resume/issues/36) | high-score job → "Tailor Resume" in sidepanel |
| **Chrome extension button** | 📋 [#37](https://github.com/narendranathe/tailor-resume/issues/37) | LinkedIn/Greenhouse/Lever |
| **JobScout webhook** | 📋 [#38](https://github.com/narendranathe/tailor-resume/issues/38) | dream job alert fires → auto-tailor |

### Tier 4 — Multi-user SaaS

| Feature | Status | Notes |
|---------|--------|-------|
| **Profile persistence** (Supabase + Pinecone) | 📋 [#39](https://github.com/narendranathe/tailor-resume/issues/39) | upload once, all future JDs pull from RAG |
| **Cover letter companion** | 📋 [#40](https://github.com/narendranathe/tailor-resume/issues/40) | same pipeline, 1-page LaTeX cover letter |
| **Subscription tiers** (Free + Pro via Stripe) | 📋 [#41](https://github.com/narendranathe/tailor-resume/issues/41) | 5/mo free · unlimited = Pro |

---

## Install

**Pip (no clone needed):**
```bash
pip install tailor-resume
tailor-resume --jd jd.txt --artifact resume.md --name "Jane Smith" --email "jane@example.com"
```

**Local clone (recommended for development):**
```bash
git clone https://github.com/narendranathe/tailor-resume ~/projects/tailor-resume
cd ~/projects/tailor-resume
pip install -r requirements.txt
python -m pytest tests/ -v   # 458+ tests, no API keys required
```

**Global Claude Code skill + MCP (use `/tailor-resume` from any project):**
```bash
git clone https://github.com/narendranathe/tailor-resume ~/projects/tailor-resume
cd ~/projects/tailor-resume
pip install -r requirements.txt
make install-global
# Restart Claude Code, then type /tailor-resume from any project
```

---

## Export to PDF

```bash
pdflatex resume.tex   # local install (MiKTeX or TeX Live)
```

Or upload `resume.tex` to [Overleaf](https://www.overleaf.com) — set compiler to **pdfLaTeX**, click Recompile, download PDF. No local LaTeX install required.

---

## For Developers

### Contributing

```bash
# 1. Fork and clone
git clone https://github.com/YOUR_USERNAME/tailor-resume

# 2. Install
pip install -r requirements.txt
pip install -r requirements-optional.txt  # mcp, pinecone, openai

# 3. Lint
python -m ruff check .claude/skills/tailor-resume/scripts/ tests/

# 4. Test (no API keys required)
python -m pytest tests/ -v
python -m pytest tests/ --cov=.claude/skills/tailor-resume/scripts --cov-report=term-missing
# Coverage threshold: 86%

# 5. Submit PR to main
```

**Before opening a PR:**
- Run `ruff check` and `pytest` locally — CI runs both on push.
- Every new script should have a corresponding `tests/test_*.py`.
- New domain concepts must be added to `UBIQUITOUS_LANGUAGE.md`.
- New features should be captured as PRDs in `specs/prd_*.md` and logged as GitHub issues before coding starts (this preserves decision memory across sessions).

**PRD → Issue → Branch → PR process:**
The project uses Product-Driven Development (PDD). Before implementing a feature:
1. Write a PRD in `specs/prd_<name>.md` (Problem → Users → Stories → Flow → Modules → Acceptance → Metrics)
2. Open a GitHub issue referencing the PRD
3. Commit the PRD file to `main` — this retains memory across Claude Code sessions
4. Implement, test, and PR against `main`

### Feedback

**File a GitHub issue** — the fastest path:
```
https://github.com/narendranathe/tailor-resume/issues/new
```

Use these labels:
- `bug` — something produces wrong output (include ATS score, JD snippet, blob snippet)
- `enhancement` — new capability (describe use case, not solution)
- `prd` — full PRD attached
- `skill-feedback` — issue with the `/tailor-resume` Claude Code skill behavior
- `ats-scoring` — ATS score doesn't match expectation (include before/after)

**For skill feedback:** Run `/tailor-resume`, paste both the JD and the output into the issue. Include the ATS score and which specific bullets you think are wrong.

---

## Project structure

```
tailor-resume/
├── .claude/
│   ├── .mcp.json                         — MCP plugin config (auto-loaded by Claude Code)
│   └── skills/tailor-resume/
│       ├── SKILL.md                      — skill instructions and 8-step workflow
│       ├── REFERENCE.md                  — 2026 resume philosophy, bullet scoring rubric
│       ├── EXAMPLES.md                   — invocation examples and blob format templates
│       ├── scripts/                      — all core pipeline logic lives here
│       │   ├── pipeline.py               — TailorConfig + TailorResult; execute() and execute_text()
│       │   ├── resume_types.py           — Profile, Role, Bullet, GapReport dataclasses
│       │   ├── parsers/
│       │   │   ├── normalizer.py         — date normalization, dedup, merge_profiles()
│       │   │   ├── plain_parser.py       — blob/plain-text parsing
│       │   │   ├── markdown_parser.py    — Markdown resume parsing
│       │   │   ├── latex_parser.py       — LaTeX resume parsing
│       │   │   ├── pdf_extractor.py      — 4-tier PDF extraction (Claude/pdfminer/pypdf/stdlib)
│       │   │   └── docx_extractor.py     — DOCX resume parsing
│       │   ├── profile_extractor.py      — compatibility shim re-exporting parsers/
│       │   ├── jd_gap_analyzer.py        — ATS score, GapSignal, GapReport
│       │   ├── latex_renderer.py         — Profile dict → Jake-template LaTeX
│       │   ├── star_validator.py         — STAR compliance scoring per Bullet
│       │   ├── ats_scorer.py             — 40% keyword + 30% category + 20% quality + 10% seniority
│       │   ├── text_utils.py             — tokenize, extract_metrics, escape, shared utilities
│       │   ├── cover_letter_renderer.py  — CoverLetterResult; template + Claude API paths
│       │   ├── github_ingester.py        — inject_github_projects(); GitHub API → Profile
│       │   ├── vault_client.py           — push_version(); version history storage
│       │   ├── api_server.py             — standalone FastAPI TRACER endpoints
│       │   ├── cli.py                    — single-command pipeline orchestrator
│       │   ├── mcp_server.py             — MCP plugin server (4 tools for Claude Code)
│       │   └── stores/
│       │       ├── rag_store.py          — PineconeStore / SQLiteStore with injected EmbedFn
│       │       └── sqlite_store.py       — local SQLite profile persistence
│       └── templates/
│           ├── resume_template.tex       — PII-free single-page LaTeX (Jake template)
│           └── cover_letter_template.tex — companion cover letter template
├── web_app/
│   ├── backend/
│   │   └── app/
│   │       ├── main.py                   — create_app() factory, mounts /api/v1 routes + CORS
│   │       ├── config.py                 — pydantic-settings; all env vars
│   │       ├── auth.py                   — Clerk RS256 JWT → user_id; dev fallback
│   │       ├── routes/
│   │       │   ├── resume.py             — POST /api/v1/resume/tailor
│   │       │   ├── profile.py            — GET/POST/DELETE /api/v1/profile
│   │       │   └── billing.py            — Stripe checkout + webhook; usage metering
│   │       ├── db/
│   │       │   └── supabase.py           — SupabaseProfileStore + SQLite fallback
│   │       └── middleware/
│   │           └── usage.py              — check_usage() / increment_usage()
│   └── frontend/                         — React (Vite + Recharts) — in progress
├── streamlit_app/
│   ├── app.py                            — 3-tab layout + sidebar save/load
│   └── tabs/
│       ├── profile_tab.py                — parse resume → structured profile
│       ├── tailor_tab.py                 — JD gap analysis + ATS score + LaTeX render
│       └── download_tab.py               — download tailored .tex
├── tests/                                — 458+ tests, no API keys required
│   ├── conftest.py                       — sys.path setup, shared fixtures
│   ├── test_profile_extractor.py         — parser unit tests
│   ├── test_jd_gap_analyzer.py           — gap analysis + ATS scoring tests
│   ├── test_latex_renderer.py            — renderer unit tests
│   ├── test_normalizer.py                — date normalization, merge_profiles() tests
│   ├── test_cli.py                       — CLI + GitHub artifact tests
│   ├── test_mcp_server.py                — 4 MCP tool tests + ingest_github
│   ├── test_api_server.py                — FastAPI endpoint tests (rate limiting, auth)
│   ├── test_billing.py                   — Stripe webhook + usage metering tests
│   └── test_rag_store.py                 — SQLite + Pinecone store tests
├── specs/                                — PRD archive (PDD memory across sessions)
│   ├── prd_ats_99.md                     — 15-bug audit fixing the ATS scoring engine
│   ├── prd_auth_security_sprint.md       — Clerk JWT auth + rate limiting
│   ├── prd_ci_web_backend_job.md         — CI test-web job
│   ├── prd_education_parser.md           — education section parsing
│   ├── prd_error_handling_sprint.md      — silent exception suppression fixes
│   ├── prd_github_ingester_wiring.md     — GitHub repo ingestion CLI + MCP wiring
│   ├── prd_pdf_extractor_sprint.md       — 4-tier PDF extraction
│   ├── prd_plain_parser_sprint.md        — plain text / blob parser
│   ├── prd_scoring_pipeline_sprint.md    — ATS scoring pipeline
│   ├── prd_template_renderer_sprint.md   — Jake-template LaTeX renderer
│   └── prd_web_routes_sprint.md          — web API routes + rate limiting
├── fixtures/
│   ├── sample_jd.txt                     — Senior Data Engineer JD
│   ├── sample_blob.txt                   — sample work experience blob
│   └── sample_profile.json               — pre-parsed profile for fast tests
├── migrations/                           — SQL migrations (Supabase)
├── server.py                             — FastMCP HTTP/SSE entrypoint (Fly.io)
├── Dockerfile                            — python:3.12-slim for Fly.io MCP
├── fly.toml                              — Fly.io config (ord region)
├── .github/workflows/
│   ├── ci.yml                            — lint + test (3.11/3.12) + test-web on push
│   └── deploy-mcp.yml                    — auto-deploy MCP to Fly.io on main push
├── Makefile                              — setup/demo/test/lint/render/install-global
├── pyproject.toml                        — PyPI package config
├── requirements.txt                      — streamlit, pytest, ruff
├── requirements-optional.txt             — pinecone-client, openai, mcp
├── UBIQUITOUS_LANGUAGE.md                — canonical DDD glossary
└── .env.example                          — documented env vars with safe defaults
```

---

## Architecture

### Data flow

```
Artifact(s) [blob | markdown | latex | pdf | docx | github]
    |
    v
parsers/ --- auto_detect_format() --- format-specific parser
    |                                  (plain_parser, markdown_parser, latex_parser,
    |                                   pdf_extractor [4 tiers], docx_extractor)
    v
merge_profiles()  <--- de-duplicate Roles by company+date
    |
    v
jd_gap_analyzer.py --- ATS score (40% keyword + 30% category + 20% quality + 10% seniority)
    |                   GapReport: top_missing GapSignals + keyword_gaps + recommendations
    v
latex_renderer.py --- build_from_profile() -> resume_template.tex -> resume.tex
    |                  (truncate_to_limit() enforces 20-word bullet cap)
    v
out/resume.tex  -->  pdflatex / Overleaf -> PDF
```

### PDF extraction tiers (silent fallback chain)

| Tier | Engine | Best for |
|------|--------|----------|
| 0 | Claude document API (`anthropic>=0.27`) | Scanned PDFs, image-only PDFs, garbled CMR fonts |
| 1 | pdfminer.six | LaTeX/CMR-font PDFs, multi-column layouts |
| 2 | pypdf | Word-generated PDFs |
| 3 | stdlib | Zero-dependency fallback |

Each tier returns `None` on failure; the chain tries the next tier silently.

### ATS scoring formula

```
ATS Score = (40% x keyword_overlap) + (30% x category_coverage) + (20% x bullet_quality) + (10% x seniority_signal)
```

- **keyword_overlap** — fraction of JD tokens that appear in the Profile (min token length: 2, so "sql", "ml", "ai", "dag" all count)
- **category_coverage** — fraction of 10 Signal Categories with at least one JD keyword matched by the Profile
- **bullet_quality** — STAR score (Action verb + measurable Result) averaged across all Bullets
- **seniority_signal** — presence of Staff/Principal/Lead/Director vocabulary in Role titles and Bullets

### ATS Relevance Gate

| Initial Score | Action |
|---|---|
| >= 80 | Proceed — target 97–100 |
| 60–79 | Proceed — honest ceiling reported at end |
| 50–59 | Proceed with gap note |
| < 50 | Decline — role doesn't align with profile |

### Web backend layout

```
web_app/backend/app/
  main.py         — create_app() factory; /api/v1 + CORS
  auth.py         — Clerk RS256 JWT -> user_id; dev fallback
  config.py       — pydantic-settings (all env vars)
  routes/
    resume.py     — POST /api/v1/resume/tailor
    profile.py    — GET/POST/DELETE /api/v1/profile
    billing.py    — Stripe checkout + webhook
  db/supabase.py  — SupabaseProfileStore + SQLite fallback (same interface)
  middleware/
    usage.py      — Free (5/mo) vs Pro (unlimited) enforcement
```

### Storage fallback pattern

Both profile storage (`db/supabase.py`) and usage metering (`middleware/usage.py`) select backend at runtime: Supabase if `SUPABASE_URL + SUPABASE_SERVICE_KEY` are set, else SQLite at `~/.tailor_resume/`. All new stores must follow this convention.

### Two separate runtimes

**CLI/skill pipeline** — zero-dependency Python in `.claude/skills/tailor-resume/scripts/`. The web backend appends the scripts dir to `sys.path` at startup so both runtimes share the same implementation without duplication.

**Web backend** — FastAPI in `web_app/backend/`. Deploy: `cd web_app && fly deploy --remote-only` → `tailor-resume-api.fly.dev`.

---

## Ubiquitous language

Canonical terms used consistently across code, tests, docs, and conversation. Full glossary: [`UBIQUITOUS_LANGUAGE.md`](UBIQUITOUS_LANGUAGE.md).

| Term | Meaning | Never say |
|------|---------|-----------|
| **Profile** | Canonical parsed representation of resume data | *resume object*, *candidate data* |
| **Role** | Single employment entry inside `Profile.experience` | *job*, *position*, *work entry* |
| **Bullet** | One achievement line inside a Role or Project | *achievement*, *line item* |
| **Artifact** | A single input file or blob fed to the pipeline (`PATH:FORMAT`) | *input*, *source file* |
| **Format** | Declared input type: `blob`, `markdown`, `latex`, `linkedin`, `pdf`, `docx` | *file type*, *mode* |
| **GapSignal** | A Signal Category where JD requires but Profile lacks coverage | *gap*, *missing skill* |
| **GapReport** | Complete gap analysis: top_missing + keyword_gaps + ats_score_estimate | *analysis result* |
| **ATS Score Estimate** | 0–100 relevance score from keyword + category + quality + seniority | *match score* |
| **Honest Ceiling** | Maximum ATS Score achievable given the candidate's actual experience | *ceiling*, *max score* |
| **Signal Category** | One of 10 capability buckets — `testing_ci_cd`, `data_quality_observability`, `orchestration`, `semantic_layer_governance`, `architecture_finops`, `streaming_realtime`, `ml_ai_platform`, `cloud_infra`, `leadership_ownership`, `sql_data_modeling` | *category*, *bucket* |
| **STAR Compliance** | Every Bullet must have Action verb (A) + measurable Result (R) | *STAR method*, *bullet quality* |
| **Bullet Formula** | `[Action verb] [what] by [method], [metric] — ≤20 words HARD LIMIT` | *XYZ format* |
| **Extraction Tier** | One of 4 ordered PDF parsing strategies (0=Claude, 1=pdfminer, 2=pypdf, 3=stdlib) | *fallback*, *method* |
| **OT1 Artifact** | Garbled character from CMR-font glyph decoded without ToUnicode CMap | *encoding artifact*, *ffi prefix* |
| **Blob** | Free-form work-history text pasted directly (no markup) | *paste*, *raw text* |
| **TailorConfig** | Immutable input dataclass for a pipeline run | *config*, *run config* |
| **TailorResult** | Output dataclass: ats_score, gap_summary, report, output_path, profile_dict | *result*, *output* |

---

## Development stages

### Phase 1 — Core pipeline (2025 Q4)
Built the deterministic pipeline from scratch: `profile_extractor.py`, `jd_gap_analyzer.py`, `latex_renderer.py`, `resume_types.py`. First ATS scoring formula. Claude Code skill and MCP plugin. Single-page Jake-template LaTeX output.

### Phase 2 — Parser hardening (2025 Q4 → 2026 Q1)
Replaced monolithic parser with modular `parsers/` package: `plain_parser`, `markdown_parser`, `latex_parser`, `pdf_extractor` (4-tier chain), `docx_extractor`, `normalizer`. Fixed OT1 artifact corruption from CMR fonts. Added `auto_detect_format()`. Wrote characterization tests capturing behavioral quirks.

### Phase 3 — ATS scoring engine (2026 Q1)
Fixed 15 bugs preventing 99+ ATS scores (`prd_ats_99.md`): `round()` instead of `int()` truncation, min token length reduced to 2 (so "sql", "ml", "etl", "dag" count), summary section uncommented in LaTeX template, STAR validator, `truncate_to_limit()` for 20-word cap, 40+ missing tools added to TOOL_VOCAB, 25+ missing action verbs, word-boundary category matching.

### Phase 4 — Web backend (2026 Q1)
FastAPI backend (`web_app/backend/`): `create_app()` factory, Clerk RS256 JWT auth, Stripe billing webhook, Supabase + SQLite fallback profile storage, usage metering middleware. Streamlit app. Hosted MCP server on Fly.io.

### Phase 5 — GitHub ingestion + cover letter (2026 Q1 → Q2)
`github_ingester.py`: fetches user repos, extracts project bullets, injects into Profile. `cover_letter_renderer.py`: CoverLetterResult with template path and Claude API path; structured error handling distinguishing `RateLimitError` from generic failures. Vault client for version history.

### Phase 6 — Error handling + security (2026 Q2)
Fixed silent exception suppression in `cover_letter_renderer.py` and `billing.py` (`prd_error_handling_sprint.md`). Clerk JWT hardening (`prd_auth_security_sprint.md`): reject `none` algorithm, validate `iss` and `azp` claims, rate-limit `/tailor` per user. API key validation for `api_server.py`.

### Phase 7 — CI infrastructure (2026 Q2)
Added `test-web` CI job (`prd_ci_web_backend_job.md`): installs FastAPI stack, runs `test_api_server.py`, `test_billing.py`, `test_web_api.py`. Fixed coverage threshold (86%). `test_mcp_server.py` skip guard for environments without `mcp` package. Fixed ruff F401 linting.

---

## Design decisions

These decisions are recorded from PRDs and issues as reasoning behind non-obvious choices.

**1. Stdlib-only core pipeline**
The pipeline uses zero third-party dependencies. Cloud features (Pinecone, OpenAI, mcp) are opt-in via `requirements-optional.txt`. This keeps the install surface minimal and ensures the tool works in any environment.

**2. EmbedFn injected at store construction, not called internally**
The RAG store accepts `EmbedFn = Callable[[str], List[float]]` at construction time. Reason: OpenAI produces 1536-dim vectors; TF-IDF produces 128-dim vectors. Mixing them in the same index corrupts cosine similarity scores silently. Injection makes the dimension contract explicit and testable.

**3. Supabase + SQLite fallback via same interface**
Profile storage and usage metering both implement the same interface and select backend at runtime from env vars. Downstream code never knows which backend is active. Local development and CI don't require a Supabase account.

**4. 4-tier PDF extraction with silent fallback**
Each tier returns `None` on failure; the chain tries the next. Real PDFs in the wild use wildly different encoding strategies. A hard failure on tier 1 would block users with tier-2-compatible PDFs.

**5. OT1 normalization post-processing on all tiers**
After any tier returns text, `_normalize_ot1_artifacts()` converts CMR-font glyph corruption (`"ffi"` prefix, lone icon characters) to real bullet symbols. LaTeX PDFs without embedded ToUnicode CMap maps are common (any Jake-template PDF) and produce garbage without this pass.

**6. Min token length = 2, not 3 (ATS keyword scoring)**
The original 3-char filter dropped "sql", "ml", "etl", "dag", "bi", "ai" from every keyword comparison. These are high-signal JD terms. Reduced to 2.

**7. STAR compliance enforced at render time via `truncate_to_limit()`**
Bullets longer than 20 words are truncated at the last punctuation boundary within a 3-word lookback window before LaTeX escaping. A 30-word bullet looks fine in the editor but renders mid-sentence in the PDF. The renderer makes the constraint visible and explicit.

**8. PRDs committed to `main` before implementation**
All PRDs are committed to `specs/` and logged as GitHub issues before coding starts. Claude Code sessions have a finite context window. If a session closes mid-sprint, the next session can read the PRD and GitHub issues to reconstruct intent without relying on conversation memory.

**9. No PII hardcoded in templates**
`resume_template.tex` contains `{{NAME}}`, `{{EMAIL}}`, `{{PHONE}}` placeholders only. All PII is injected at runtime via `render_template()`. Templates committed to a public repo must never contain personal data.

---

## Errors encountered and how we fixed them

Real production errors from the issue tracker and PRDs, preserved as institutional memory.

**ATS score hard-capped at 99** (`prd_ats_99.md`)
`int(score * 100)` truncates 0.999 to 99. A perfectly matched resume could never score 100. Fixed: `round(score * 100)`.

**"sql", "ml", "etl" silently excluded from keyword overlap** (`prd_ats_99.md`)
3-char min token filter dropped all 3-letter keywords. JDs heavy on "SQL Spark ETL" scored 0 keyword overlap on those exact terms. Fixed: reduced min length to 2.

**Summary section missing from every rendered PDF** (`prd_ats_99.md`)
`% \section{Summary}` was commented out in `resume_template.tex`. Every resume silently omitted the most ATS-critical section. Fixed: uncommented; added `{{SUMMARY}}` placeholder.

**OT1 glyph corruption** (`prd_pdf_extractor_sprint.md`)
Jake-template PDFs exported without embedded ToUnicode CMap decoded CMR bullet glyphs (0x0F) as `"ffi"`. Every bullet in a self-generated PDF started with `"ffi"`. Fixed: `_normalize_ot1_artifacts()` post-processing pass on all tiers.

**Education arg order transposed** (`prd_education_parser.md`)
`\resumeSubheading{institution}{location}{degree}{dates}` — the renderer was passing `{institution}{degree}{location}{dates}`. Location and degree were swapped in every rendered PDF. Fixed: matched arg order to Jake-template macro signature.

**Silent cover letter failures** (`prd_error_handling_sprint.md`)
`cover_letter_renderer.py` caught every exception with `except Exception: pass`, discarded the error, and returned a template letter with no indication of failure. Fixed: split into `except anthropic.RateLimitError` (warning log, template fallback) and `except Exception` (exception log with stack trace).

**Stripe subscription cancellation silent drop** (`prd_error_handling_sprint.md`)
`billing.py::_revert_plan_by_customer()` wrapped Supabase in `except Exception: pass`, returned silently, and the webhook handler still returned HTTP 200. Stripe marked the event delivered and never retried. Cancelled subscribers retained Pro access indefinitely. Fixed: exception logged, HTTP 500 returned on failure so Stripe retries.

**CI `test-web` exit code 2** (`prd_ci_web_backend_job.md`)
`test_api_server.py` made real pipeline calls without mocking — pytest was interrupted during collection. Fixed: autouse `_patch_pipeline` fixture patches all pipeline functions before any test runs.

**`mcp` package not installed in `test-web` CI environment**
`test_mcp_server.py` imported `mcp_server` at module level. The test-web job installs only FastAPI deps. Collection failed → exit code 2. Fixed: `try/except ImportError` guard at module level with `pytest.skip(allow_module_level=True)`.

**Coverage 77.5% < 86% threshold**
Three causes: (1) `api_server.py` measured at 0% — excluded via `.coveragerc omit` (it's an ASGI binary, not a library). (2) `build_docx_from_profile()` had 0 tests — added 12. (3) `cli.py` GitHub artifact path and `mcp_server.py::ingest_github` untested — added `TestCliGitHubArtifact` and `TestIngestGithub`.

---

## Key environment variables

| Variable | Used by | Default | Notes |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | pdf_extractor (Tier 0), cover_letter_renderer, api_server | None | Required for Claude-powered features; core pipeline works without it |
| `PINECONE_API_KEY` | stores/ | None | Optional; SQLite used as fallback |
| `OPENAI_API_KEY` | stores/ | None | Optional; TF-IDF embeddings used as fallback |
| `SUPABASE_URL` | web_app/backend/db/supabase.py | None | Optional; SQLite at `~/.tailor_resume/` used as fallback |
| `SUPABASE_SERVICE_KEY` | web_app/backend/db/supabase.py | None | Optional |
| `STRIPE_WEBHOOK_SECRET` | web_app/backend/routes/billing.py | None | Required for Stripe webhook signature verification |
| `CLERK_PEM_KEY` | web_app/backend/auth.py | None | Required in production; dev fallback active when unset |
| `TAILOR_PDF_MODEL` | pdf_extractor (Tier 0) | `claude-haiku-4-5-20251001` | Override with `claude-sonnet-4-6` for higher accuracy |
| `API_KEY` | api_server.py | `dev-key` | HTTP API key for standalone TRACER endpoints |
| `DEV_MODE` | api_server.py | `false` | Disables auth in development |

---

## Design principles

- **No PII hardcoded** — all personal data passed at runtime, never committed
- **No fabrication** — Claude only reframes evidence you provide; never invents metrics
- **Zero-config default** — core pipeline runs on stdlib only; cloud features are opt-in
- **Single page** — forces prioritization; the constraint is the feature
- **Factual integrity** — if a metric is missing, Claude asks for it rather than guessing
- **Degradation over failure** — every external dependency (Supabase, Pinecone, Claude API) has a local fallback
- **PRDs before code** — every non-trivial feature has a PRD in `specs/` committed before implementation
