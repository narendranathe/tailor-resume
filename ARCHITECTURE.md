# Architecture

Technical reference for tailor-resume: data flow, ATS formula, file structure, ubiquitous language, development history, design decisions, and a log of production errors and how they were fixed.

---

## Data flow

```
Artifact(s)  [blob | markdown | latex | pdf | docx | github]
    │
    ▼
parsers/  ── auto_detect_format() ── format-specific parser
    │          (plain_parser, markdown_parser, latex_parser,
    │           pdf_extractor [4 tiers], docx_extractor)
    ▼
merge_profiles()  ←── de-duplicate Roles by company+date
    │
    ▼
jd_gap_analyzer.py  ── ATS score + GapReport
    │                    (top_missing GapSignals, keyword_gaps, recommendations)
    ▼
latex_renderer.py  ── build_from_profile() → resume_template.tex → resume.tex
    │                  (truncate_to_limit() enforces 20-word bullet cap)
    ▼
out/resume.tex  ──►  pdflatex / Overleaf → PDF
```

---

## ATS scoring formula

```
ATS Score = (40% × keyword_overlap)
          + (30% × category_coverage)
          + (20% × bullet_quality)
          + (10% × seniority_signal)
```

| Component | What it measures |
|---|---|
| `keyword_overlap` | Fraction of JD tokens present in the Profile. Min token length: 2 — so "sql", "ml", "ai", "dag" all count. |
| `category_coverage` | Fraction of 10 Signal Categories with ≥1 JD keyword matched by the Profile. |
| `bullet_quality` | STAR score (Action verb + measurable Result) averaged across all Bullets. |
| `seniority_signal` | Presence of Staff/Principal/Lead/Director vocabulary in Role titles and Bullets. |

**Signal Categories:** `testing_ci_cd` · `data_quality_observability` · `orchestration` · `semantic_layer_governance` · `architecture_finops` · `streaming_realtime` · `ml_ai_platform` · `cloud_infra` · `leadership_ownership` · `sql_data_modeling`

**ATS Relevance Gate:**

| Score | Action |
|---|---|
| ≥ 80 | Proceed — target 97–100 |
| 60–79 | Proceed — honest ceiling reported at end |
| 50–59 | Proceed with gap note |
| < 50 | Decline — role doesn't align with profile |

---

## PDF extraction tiers

Four-tier chain with silent fallback. Each tier returns `None` on failure; the chain tries the next.

| Tier | Engine | Best for |
|---|---|---|
| 0 | Claude document API (`anthropic>=0.27`) | Scanned/image-only PDFs, garbled CMR fonts |
| 1 | pdfminer.six | LaTeX/CMR-font PDFs, multi-column layouts |
| 2 | pypdf | Word-generated PDFs |
| 3 | stdlib | Zero-dependency fallback |

**OT1 normalization** runs on the output of every tier: `_normalize_ot1_artifacts()` converts CMR-font glyph corruption (the CMR bullet glyph 0x0F decodes as `"ffi"` without a ToUnicode CMap) to real bullet symbols.

---

## Two runtimes, one implementation

**CLI/skill pipeline** — zero-dependency Python in `.claude/skills/tailor-resume/scripts/`. `pipeline.py` is the entry point. `cli.py` and `mcp_server.py` both delegate to it.

**Web backend** — FastAPI in `web_app/backend/`. At startup, `main.py` appends the scripts dir to `sys.path` so both runtimes share the same pipeline implementation without duplication. Deploy: `fly deploy --remote-only` → `tailor-resume-api.fly.dev`.

**Storage fallback pattern:** Profile storage (`db/supabase.py`) and usage metering (`middleware/usage.py`) both implement the same interface. Backend selected at runtime: Supabase if `SUPABASE_URL + SUPABASE_SERVICE_KEY` are set, else SQLite at `~/.tailor_resume/`. All new stores must follow this convention.

---

## File structure

```
tailor-resume/
├── .claude/skills/tailor-resume/
│   ├── SKILL.md                      — skill instructions and 8-step workflow
│   ├── REFERENCE.md                  — 2026 resume philosophy, bullet scoring rubric
│   ├── scripts/
│   │   ├── pipeline.py               — TailorConfig + TailorResult; execute() / execute_text()
│   │   ├── resume_types.py           — Profile, Role, Bullet, GapReport dataclasses
│   │   ├── parsers/
│   │   │   ├── normalizer.py         — date normalization, dedup, merge_profiles()
│   │   │   ├── plain_parser.py       — blob/plain-text parsing
│   │   │   ├── markdown_parser.py    — Markdown resume parsing
│   │   │   ├── latex_parser.py       — LaTeX resume parsing
│   │   │   ├── pdf_extractor.py      — 4-tier PDF extraction
│   │   │   └── docx_extractor.py     — DOCX resume parsing
│   │   ├── profile_extractor.py      — compatibility shim re-exporting parsers/
│   │   ├── jd_gap_analyzer.py        — ATS score, GapSignal, GapReport
│   │   ├── latex_renderer.py         — Profile dict → Jake-template LaTeX
│   │   ├── star_validator.py         — STAR compliance scoring per Bullet
│   │   ├── ats_scorer.py             — four-component ATS formula
│   │   ├── text_utils.py             — tokenize, extract_metrics, escape
│   │   ├── cover_letter_renderer.py  — CoverLetterResult; template + Claude API paths
│   │   ├── github_ingester.py        — inject_github_projects(); GitHub API → Profile
│   │   ├── vault_client.py           — push_version(); resume version history
│   │   ├── api_server.py             — standalone FastAPI TRACER endpoints
│   │   ├── cli.py                    — single-command pipeline orchestrator
│   │   ├── mcp_server.py             — MCP plugin server (4 tools: extract_profile, analyze_gap, render_latex, run_pipeline)
│   │   └── stores/
│   │       ├── rag_store.py          — PineconeStore / SQLiteStore with injected EmbedFn
│   │       └── sqlite_store.py       — local SQLite profile persistence
│   └── templates/
│       ├── resume_template.tex       — PII-free single-page LaTeX (Jake template)
│       └── cover_letter_template.tex — companion cover letter template
├── web_app/
│   ├── backend/app/
│   │   ├── main.py                   — create_app() factory; /api/v1 + CORS
│   │   ├── config.py                 — pydantic-settings; all env vars
│   │   ├── auth.py                   — Clerk RS256 JWT → user_id; dev fallback
│   │   ├── routes/
│   │   │   ├── resume.py             — POST /api/v1/resume/tailor
│   │   │   ├── profile.py            — GET/POST/DELETE /api/v1/profile
│   │   │   └── billing.py            — Stripe checkout + webhook; usage metering
│   │   ├── db/supabase.py            — SupabaseProfileStore + SQLite fallback
│   │   └── middleware/usage.py       — Free (5/mo) vs Pro (unlimited) enforcement
│   └── frontend/                     — React (Vite + Recharts) — in progress
├── streamlit_app/
│   ├── app.py                        — 3-tab layout + sidebar save/load
│   └── tabs/                         — profile_tab, tailor_tab, download_tab
├── tests/                            — 458+ tests, no API keys required
├── specs/                            — PRD archive (PDD memory across sessions)
├── fixtures/                         — sample JD, blob, profile JSON
├── migrations/                       — Supabase SQL migrations
├── server.py                         — FastMCP HTTP/SSE entrypoint (Fly.io MCP)
├── Dockerfile                        — python:3.12-slim for Fly.io
├── fly.toml                          — Fly.io config (ord region)
└── .github/workflows/
    ├── ci.yml                        — lint + test (3.11/3.12) + test-web on push
    └── deploy-mcp.yml                — auto-deploy MCP to Fly.io on main push
```

---

## Ubiquitous language

One canonical term per concept. Aliases are listed to be avoided. Full glossary: [`UBIQUITOUS_LANGUAGE.md`](UBIQUITOUS_LANGUAGE.md).

| Term | Definition | Avoid |
|---|---|---|
| **Profile** | Canonical parsed resume data: `experience`, `projects`, `skills`, `education`, `certifications` | *resume object, candidate data* |
| **Role** | Single employment entry inside `Profile.experience` | *job, position, work entry* |
| **Bullet** | One achievement line inside a Role or Project. Has `text`, `metrics`, `tools`, `evidence_source`, `confidence` | *achievement, line item* |
| **Artifact** | A single input file or blob fed to the pipeline, identified as `PATH:FORMAT` | *input, source file* |
| **GapSignal** | A Signal Category where JD requires but Profile lacks coverage | *gap, missing skill* |
| **GapReport** | Complete gap analysis: `top_missing` + `keyword_gaps` + `ats_score_estimate` + `recommendations` | *analysis result* |
| **ATS Score Estimate** | 0–100 relevance estimate — not a real ATS system's score | *match score* |
| **Honest Ceiling** | Maximum ATS Score achievable given the candidate's actual experience | *ceiling, max score* |
| **STAR Compliance** | Every Bullet must have Action verb (A) + measurable Result (R). Situation/Task implied by the Role header | *STAR method* |
| **Bullet Formula** | `[Action verb] [what] by [method], [metric] — ≤20 words HARD LIMIT` | *XYZ format* |
| **Extraction Tier** | One of 4 ordered PDF parsing strategies (0=Claude, 1=pdfminer, 2=pypdf, 3=stdlib) | *fallback, method* |
| **OT1 Artifact** | Garbled character from CMR-font glyph decoded without ToUnicode CMap (e.g. `"ffi"`) | *encoding artifact* |
| **TailorConfig** | Immutable input dataclass for a pipeline run | *config* |
| **TailorResult** | Output dataclass: `ats_score`, `gap_summary`, `report`, `output_path`, `profile_dict` | *result, output* |

---

## Key environment variables

| Variable | Default | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | None | Required for Tier 0 PDF, cover letter, api_server. Core pipeline works without it. |
| `PINECONE_API_KEY` | None | Optional — SQLite used as fallback |
| `OPENAI_API_KEY` | None | Optional — TF-IDF embeddings used as fallback |
| `SUPABASE_URL` | None | Optional — SQLite at `~/.tailor_resume/` used as fallback |
| `SUPABASE_SERVICE_KEY` | None | Optional |
| `STRIPE_WEBHOOK_SECRET` | None | Required for Stripe webhook signature verification |
| `CLERK_PEM_KEY` | None | Required in production. Dev fallback active when unset. |
| `TAILOR_PDF_MODEL` | `claude-haiku-4-5-20251001` | Override Claude model for Tier 0. Set to `claude-sonnet-4-6` for higher accuracy. |
| `API_KEY` | `dev-key` | HTTP API key for `api_server.py` TRACER endpoints |
| `DEV_MODE` | `false` | Set `true` to disable auth in development |

---

## Development stages

### Phase 1 — Core pipeline (2025 Q4)
Built the deterministic pipeline: `profile_extractor.py`, `jd_gap_analyzer.py`, `latex_renderer.py`, `resume_types.py`. First ATS scoring formula. Claude Code skill and MCP plugin. Single-page Jake-template LaTeX output.

### Phase 2 — Parser hardening (2025 Q4 → 2026 Q1)
Replaced monolithic parser with modular `parsers/` package: plain_parser, markdown_parser, latex_parser, pdf_extractor (4-tier chain), docx_extractor, normalizer. Fixed OT1 artifact corruption from CMR fonts. Added `auto_detect_format()`. Wrote characterization tests capturing behavioral quirks.

### Phase 3 — ATS scoring engine (2026 Q1)
Fixed 15 bugs preventing 99+ ATS scores (`prd_ats_99.md`): `round()` instead of `int()` truncation, min token length 3→2 (so "sql", "ml", "etl", "dag" count), summary section uncommented in LaTeX template, STAR validator, `truncate_to_limit()` for 20-word bullet cap, 40+ missing tools added to TOOL_VOCAB, word-boundary category matching.

### Phase 4 — Web backend (2026 Q1)
FastAPI backend: `create_app()` factory, Clerk RS256 JWT auth, Stripe billing webhook, Supabase + SQLite fallback profile storage, usage metering middleware. Streamlit app. Hosted MCP server on Fly.io.

### Phase 5 — GitHub ingestion + cover letter (2026 Q1 → Q2)
`github_ingester.py` fetches user repos, extracts project bullets, injects into Profile. `cover_letter_renderer.py` adds CoverLetterResult with template and Claude API paths. Vault client for version history.

### Phase 6 — Error handling + security (2026 Q2)
Fixed silent exception suppression in `cover_letter_renderer.py` and `billing.py` (`prd_error_handling_sprint.md`). Clerk JWT hardening: reject `none` algorithm, validate `iss` and `azp` claims, rate-limit `/tailor` per user. API key validation for `api_server.py`.

### Phase 7 — CI infrastructure (2026 Q2)
Added `test-web` CI job: installs FastAPI stack, runs `test_api_server.py`, `test_billing.py`, `test_web_api.py`. Fixed 86% coverage threshold. Skip guard for `mcp` package in environments without it. Fixed ruff F401 linting.

---

## Design decisions

Reasoning behind non-obvious choices, drawn directly from PRDs.

**Stdlib-only core pipeline.** Zero third-party dependencies for `pipeline.py`, `jd_gap_analyzer.py`, `latex_renderer.py`. Cloud features are opt-in via `requirements-optional.txt`. The tool works in any environment without setup.

**EmbedFn injected at store construction.** The RAG store accepts `EmbedFn = Callable[[str], List[float]]` at construction rather than calling OpenAI internally. OpenAI produces 1536-dim vectors; TF-IDF produces 128-dim. Mixing them in the same index corrupts cosine similarity silently. Injection makes the dimension contract explicit and testable.

**Supabase + SQLite via the same interface.** Profile storage and usage metering select backend at runtime from env vars. Downstream code never knows which backend is active. CI and local dev work without a Supabase account.

**4-tier PDF extraction with silent fallback.** Each tier returns `None` on failure. Real PDFs use wildly different encoding strategies. A hard failure on tier 1 would block users whose PDFs are tier-2 compatible.

**OT1 normalization on all extraction tiers.** Jake-template PDFs without embedded ToUnicode CMap maps (common for self-generated LaTeX PDFs) decode the CMR bullet glyph as `"ffi"`. The normalization pass runs after every tier so the caller never sees corrupt text.

**Min token length = 2, not 3.** The original 3-char filter silently dropped "sql", "ml", "etl", "dag", "bi", "ai" from every keyword comparison — exactly the most signal-dense terms in data engineering JDs.

**STAR compliance enforced at render time.** `truncate_to_limit()` trims bullets to 20 words at the last punctuation boundary before LaTeX escaping. A 30-word bullet looks fine in the editor but renders mid-sentence in the PDF. Making the constraint visible at render time prevents silent truncation.

**PRDs committed to `main` before implementation.** Claude Code sessions have a finite context window. If a session closes mid-sprint, the next session reads `specs/` and GitHub issues to reconstruct intent. PRDs are the persistent memory layer.

**No PII in templates.** `resume_template.tex` uses `{{NAME}}`, `{{EMAIL}}`, `{{PHONE}}` placeholders. All PII is injected at runtime by `render_template()`. Templates in a public repo must never contain personal data.

---

## Errors encountered and how we fixed them

Production errors preserved as institutional memory.

**ATS score hard-capped at 99** — `int(score * 100)` truncates 0.999 to 99. A perfectly matched resume couldn't score 100. Fixed: `round(score * 100)`. (`prd_ats_99.md`)

**"sql", "ml", "etl" excluded from keyword overlap** — 3-char min token filter silently dropped all 3-letter keywords. JDs dense in "SQL", "ETL", "ML" scored 0 keyword overlap on those exact terms. Fixed: min length reduced to 2. (`prd_ats_99.md`)

**Summary section missing from every PDF** — `% \section{Summary}` commented out in `resume_template.tex`. Every resume omitted the most ATS-critical section. Fixed: uncommented; added `{{SUMMARY}}` placeholder. (`prd_ats_99.md`)

**OT1 glyph corruption** — Jake-template PDFs without ToUnicode CMap decoded CMR bullet glyphs (0x0F) as `"ffi"`. Every bullet in a self-generated PDF started with `"ffi"`. Fixed: `_normalize_ot1_artifacts()` post-processing. (`prd_pdf_extractor_sprint.md`)

**Education arg order transposed** — `\resumeSubheading{institution}{location}{degree}{dates}` but the renderer was passing location and degree swapped. Fixed: matched Jake-template macro signature. (`prd_education_parser.md`)

**Silent cover letter failures** — `except Exception: pass` discarded every error. Support couldn't distinguish a rate-limit hit from a code bug. Fixed: split into `RateLimitError` (warning log + template fallback) and `Exception` (exception log with stack trace). (`prd_error_handling_sprint.md`)

**Stripe cancellation silent drop** — `_revert_plan_by_customer()` swallowed Supabase errors; webhook returned HTTP 200 so Stripe never retried. Cancelled subscribers retained Pro indefinitely. Fixed: exception logged, HTTP 500 returned on failure. (`prd_error_handling_sprint.md`)

**CI `test-web` exit code 2** — `test_api_server.py` made real pipeline calls without mocking; pytest was interrupted during collection. Fixed: autouse `_patch_pipeline` fixture patches all pipeline functions before any test runs. (`prd_ci_web_backend_job.md`)

**`mcp` package missing in `test-web` CI** — `test_mcp_server.py` imported at module level; test-web installs only FastAPI deps. Collection failed → exit code 2. Fixed: `try/except ImportError` guard with `pytest.skip(allow_module_level=True)`. (`prd_ci_web_backend_job.md`)

**Coverage 77.5% < 86% threshold** — Three causes: `api_server.py` measured at 0% (excluded via `.coveragerc omit`); `build_docx_from_profile()` had 0 tests (added 12); CLI GitHub path and `ingest_github` untested (added `TestCliGitHubArtifact` and `TestIngestGithub`). (`prd_ci_web_backend_job.md`)
