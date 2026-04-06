# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Ubiquitous Language

`UBIQUITOUS_LANGUAGE.md` is the canonical DDD glossary for this project. Always use the terms defined there consistently across code, tests, docs, and conversation.

**Auto-invoke `/ubiquitous-language` when:**
- A new domain concept, data structure, or canonical term is introduced or renamed
- Starting a session in this repo (merge any new terms discovered in the previous session)
- After an auto-compact (re-merge terms from the compacted context)
- The user says "update the glossary", "add this term", or "update ubiquitous language"

## Commands

```bash
# Dev setup
pip install -r requirements.txt          # core (stdlib-only pipeline)
pip install -r requirements-optional.txt # pinecone, openai, mcp

# Tests (no API keys required)
python -m pytest tests/ -v
python -m pytest tests/test_profile_extractor.py -v   # single file
python -m pytest tests/ --cov=.claude/skills/tailor-resume/scripts --cov-report=term-missing

# Web backend tests — need SA conda env + PYTHONPATH (fastapi/pydantic-settings not in base env)
PYTHONPATH=web_app/backend /c/Users/naren/anaconda3/envs/SA/python.exe -m pytest tests/test_billing.py tests/test_web_api.py -v

# Lint
python -m ruff check .claude/skills/tailor-resume/scripts/ tests/

# Demo pipeline → out/resume.tex
make demo

# Compile .tex → .pdf (requires pdflatex)
make render

# Install as global Claude Code skill + MCP server (run once after clone)
make install-global
```

```bash
# Web backend (web_app/backend/)
cd web_app/backend
pip install -r requirements.txt
uvicorn app.main:app --factory --reload --port 8000
```

```bash
# React frontend (web_app/frontend/)
cd web_app/frontend
npm install && npm run dev
```

## Architecture

### Two separate runtimes

**1. CLI / skill pipeline** — zero-dependency Python, lives in `.claude/skills/tailor-resume/scripts/`.
This is the core logic. `main.py` is in `web_app/backend/app/` and appends the scripts dir to `sys.path` at startup so both the web backend and CLI share the same implementation.

**2. Web backend** — FastAPI in `web_app/backend/`. Uses the `create_app()` factory (mirrors autoapply-ai). Clerk RS256 JWT auth via `X-Clerk-User-Id` header. Deploy: `cd web_app && fly deploy --remote-only` → `tailor-resume-api.fly.dev`.

### Pipeline flow

```
artifact(s) → parsers/ → merge_profiles() → jd_gap_analyzer → latex_renderer → .tex
```

- **`pipeline.py`**: `TailorConfig` + `TailorResult` dataclasses; `execute()` for file-based (CLI), `execute_text()` for text-based (MCP/API).
- **`parsers/`**: format-specific extractors — `latex_parser`, `pdf_extractor`, `plain_parser`, `markdown_parser`, `docx_extractor`, `normalizer`. `profile_extractor.py` is a compatibility shim re-exporting everything.
- **`stores/`**: RAG profile storage. `EmbedFn = Callable[[str], List[float]]` is injected at construction to prevent OpenAI (1536-dim) / TF-IDF (128-dim) mismatch corrupting cosine scores. `get_store()` returns PineconeStore if `PINECONE_API_KEY` is set, else SQLiteStore. `rag_store.py` is a compatibility shim.
- **`jd_gap_analyzer.py`**: scores each JD requirement against profile, produces ATS score + gap report.
- **`latex_renderer.py`**: Jake-template LaTeX renderer. Education arg order is `{institution}{location}{degree}{dates}`.
- **`resume_types.py`**: `Profile`, `Role`, `GapReport` dataclasses shared across all scripts.

### ATS score bands

`≥ 0.80` → "Strong match" | `0.60–0.79` → "Good match" | `0.50–0.59` → "Borderline" | `< 0.50` → decline (no .tex produced).

### Web backend layout

```
web_app/backend/app/
  config.py       # pydantic-settings; CLERK_PEM_KEY, SUPABASE_*, PINECONE_*, STRIPE_*, ANTHROPIC_API_KEY
  main.py         # create_app() factory; mounts /api/v1 routes + CORS
  auth.py         # Clerk RS256 JWT → user_id; dev fallback when CLERK_PEM_KEY unset
  routes/
    resume.py     # POST /api/v1/resume/tailor  (runs pipeline, enforces usage limit)
    profile.py    # GET/POST/DELETE /api/v1/profile  (Supabase + SQLite fallback)
    billing.py    # GET /api/v1/usage, POST /api/v1/billing/checkout + /webhook (Stripe)
  db/
    supabase.py   # SupabaseProfileStore + _SQLiteProfileStore fallback; get_profile_store()
  middleware/
    usage.py      # check_usage() / increment_usage() — Free (5/mo) vs Pro (unlimited)
```

### Storage fallback pattern

Both profile storage (`db/supabase.py`) and usage metering (`middleware/usage.py`) follow the same pattern: Supabase if `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` are set, else SQLite at `~/.tailor_resume/`. New stores should match this convention.

### MCP server

`mcp_server.py` exposes 4 typed MCP tools over stdio. Registered globally via `make mcp-install-global` (writes to `~/.claude/.mcp.json`). Delegates to `pipeline.execute_text()`.

### Tests

All 458+ tests live in `tests/`. `conftest.py` inserts the scripts dir into `sys.path` so imports work without installing the package. Tests require no API keys — all external calls are mocked. The `_regression` test files are characterization tests capturing behavioral quirks; change them only deliberately.

### Migrations

SQL migrations are in `migrations/` (plain `.sql` files, applied manually or via Supabase dashboard). `001_user_profiles.sql` → `user_profiles` table. `002_usage_and_billing.sql` → `usage` table + `plan`/`stripe_customer_id` columns on `user_profiles`.
