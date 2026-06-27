# Contributing

## Setup

```bash
git clone https://github.com/narendranathe/tailor-resume
cd tailor-resume
pip install -r requirements.txt
pip install -r requirements-optional.txt   # mcp, pinecone, openai

# Verify
python -m pytest tests/ -v                 # 458+ tests, no API keys required
python -m ruff check .claude/skills/tailor-resume/scripts/ tests/
```

## Before you write code

This project uses **Product-Driven Development (PDD)**. Before implementing a feature:

1. Write a PRD in `specs/prd_<name>.md` — use the template: Problem → Users → Stories → Flow → Modules → Acceptance → Metrics
2. Open a GitHub issue referencing the PRD
3. Commit the PRD to `main` — this is the persistent memory layer across Claude Code sessions
4. Implement, test, PR against `main`

This isn't bureaucracy. Claude Code sessions have a finite context window. A committed PRD means the next session can reconstruct intent without relying on conversation history.

## Test commands

```bash
# Full suite
python -m pytest tests/ -v

# Coverage (threshold: 86%)
python -m pytest tests/ --cov=.claude/skills/tailor-resume/scripts --cov-report=term-missing

# Web backend tests (requires FastAPI deps)
PYTHONPATH=web_app/backend python -m pytest tests/test_billing.py tests/test_web_api.py tests/test_api_server.py -v

# Single file
python -m pytest tests/test_jd_gap_analyzer.py -v

# Lint
python -m ruff check .claude/skills/tailor-resume/scripts/ tests/
```

## Conventions

- Every new script needs a corresponding `tests/test_*.py`.
- New domain concepts go in `UBIQUITOUS_LANGUAGE.md` first. Use the canonical terms in code, tests, and docs — never the aliases.
- All external dependencies (Supabase, Pinecone, Claude API) must have a local fallback. See the storage fallback pattern in `ARCHITECTURE.md`.
- No PII hardcoded anywhere. Name, email, phone are runtime-only.
- `api_server.py` is excluded from the main coverage run (it's an ASGI binary, covered separately by `test-web` CI). Don't add it back to `.coveragerc`.

## Filing feedback

Open a [GitHub issue](https://github.com/narendranathe/tailor-resume/issues/new) with the right label:

| Label | When | What to include |
|---|---|---|
| `bug` | Wrong output | ATS score + JD snippet + blob/resume snippet |
| `enhancement` | New capability | Use case description, not solution |
| `prd` | Full spec | PRD file committed to `specs/` |
| `skill-feedback` | Bad skill behavior | JD + full output + which bullets are wrong |
| `ats-scoring` | Score doesn't match expectation | Expected vs actual score, input snippets |

For skill feedback specifically: run `/tailor-resume`, copy the JD and the full output into the issue. Include the ATS score printed at the end and the specific bullets you believe are wrong or weak.
