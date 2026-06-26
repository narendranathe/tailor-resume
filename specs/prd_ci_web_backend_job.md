## Problem

The current CI workflow (`ci.yml`) installs only `requirements.txt` and `requirements-dev.txt`, which omits `web_app/backend/requirements.txt` (FastAPI, pydantic-settings, Stripe, Supabase, etc.). As a result, six test files — `test_billing.py`, `test_web_api.py`, `test_api_server.py`, `test_setup_routes.py`, `test_profile_patch.py`, and `test_mcp_server.py` — are silently skipped on every CI run via `pytest.importorskip` and module-level `pytest.skip` guards. Any regression in the billing tier logic, Clerk auth middleware, usage metering, or FastAPI route layer goes completely undetected in CI, allowing broken web-backend code to merge to `main` unnoticed and reach production at `tailor-resume-api.fly.dev`.

## Users

| Persona | Resume source / entry point | Impact |
|---|---|---|
| Developer / contributor | Pull request → GitHub Actions CI | Gets false-green CI; broken web API routes ship to production silently |
| End user (free tier) | Browser → POST /api/v1/resume/tailor | Usage limit enforcement bug could allow unlimited free tailors or block paying users |
| End user (pro subscriber) | Stripe checkout → POST /api/v1/billing/checkout | Checkout URL regression goes undetected; subscription flow breaks |

## User Stories

1. As a contributor, I want CI to run the web backend tests when I open a PR, so that billing/auth/route regressions are caught before merge.
2. As a developer, I want ImportError regressions in the FastAPI app to fail CI immediately, so I know when a dependency is broken or missing from `web_app/backend/requirements.txt`.
3. As a free-tier user, I want the 5-tailors-per-month enforcement to be covered by a CI test, so that usage metering logic stays correct across refactors.

## Flow

```
BEFORE
──────
push/PR → ci.yml (job: test)
            pip install requirements.txt requirements-dev.txt
            pytest tests/                    ← test_billing.py, test_web_api.py skipped (importorskip)
            Result: ✅ green even when web backend is broken

AFTER
─────
push/PR → ci.yml (job: test)          ci.yml (job: test-web)
            pip install core deps   │    pip install core deps
            pytest tests/ -v        │    pip install web_app/backend/requirements.txt
            (same as before)        │    PYTHONPATH=web_app/backend pytest
                                    │      tests/test_billing.py
                                    │      tests/test_web_api.py
                                    │      tests/test_api_server.py
                                    │      tests/test_setup_routes.py
                                    │      tests/test_profile_patch.py
                                    │      tests/test_mcp_server.py
                                    │    Result: ❌ fails on ImportError or regression
```

## Modules

| File | Line range | Exact change description |
|---|---|---|
| `.github/workflows/ci.yml` | 9–44 (append after existing `test` job) | Add new `test-web` job: checkout, Python 3.11, pip install core + web backend deps, pytest the six web/mcp test files with `PYTHONPATH=web_app/backend` and test env vars |

## Acceptance Criteria

- [ ] A new `test-web` job appears in `ci.yml` and runs on `ubuntu-latest` with Python 3.11.
- [ ] The job installs both `requirements.txt -r requirements-dev.txt` AND `web_app/backend/requirements.txt` before running pytest.
- [ ] `pytest` is invoked with `PYTHONPATH=web_app/backend` and targets all six web/mcp test files explicitly; it must exit 0 in a fresh environment where no real API keys are set.
- [ ] The YAML passes `python -c "import yaml; yaml.safe_load(open('…/ci.yml'))"` with no errors.
- [ ] Individual tests that require real Supabase/Stripe/Clerk credentials are skipped (not errored) via existing `monkeypatch.setenv` + dev-fallback auth patterns in the test files.
- [ ] The existing `test` matrix job (Python 3.11 + 3.12) is unchanged.

## Metrics

| Metric | Before | After |
|---|---|---|
| Tests collected from web backend files | 0 (all skipped via importorskip) | ~60+ tests collected |
| CI false-green risk for FastAPI ImportError | High — ImportError causes skip, not fail | None — ImportError propagates as collection error |
| Billing / usage metering test coverage in CI | 0% | 100% of `test_billing.py` (11 tests) |
| Web API route coverage in CI | 0% | 100% of `test_web_api.py` (13 tests) |
| CI job count | 1 (matrix: 2 runs) | 2 jobs (matrix: 2 runs + 1 web run) |
