# PRD: Fix Billing Test Failures by Adding importorskip Guards for Web Backend Deps

**Category:** billing-web-deps
**Effort:** Trivial
**Date:** 2026-06-25

---

## Problem

The billing test suite (`tests/test_billing.py`) fails with 11 errors in the base/default Python environment because `pydantic_settings` and `fastapi` are listed in `web_app/backend/requirements.txt` but are absent from the root `requirements.txt` and `requirements-optional.txt`. When pytest collects the module, two chained `ModuleNotFoundError` exceptions abort import entirely: the first fires when `app.config` attempts to import `pydantic_settings`, causing 8 test failures; the second fires when `app.middleware.usage` attempts to import `fastapi`, causing the remaining 3 `TestSQLiteUsageStore` failures. CLAUDE.md explicitly documents that billing tests must run under the `SA` conda environment, yet nothing in the test file enforces or communicates this boundary. Every developer running `pytest` in the base env sees 11 loud failures that are not real regressions, eroding trust in the test suite and wasting triage time. CI pipelines not configured with the SA env also fail on every run.

---

## Users

| Persona | Environment | Impact |
|---|---|---|
| Local developer (base env) | Default Python / venv | Sees 11 import errors on every `pytest` run; wastes time triaging false failures |
| CI pipeline (non-SA runner) | GitHub Actions / default runner | Billing tests fail every build; PR gates are unreliable |
| Local developer (SA conda env) | `SA` conda env with backend deps installed | Unaffected today; must remain fully green after the fix |
| End user / customer | Production web app | Indirectly affected if broken CI allows regressions to ship |

---

## Stories

1. **As a developer running tests in the base Python environment**, I want billing tests to be skipped (not failed) when `pydantic_settings` and `fastapi` are not installed, so that I can distinguish genuine regressions from environment-setup gaps without reading CLAUDE.md first.

2. **As a CI pipeline running on a default runner**, I want the billing test module to produce clear skip output instead of import errors, so that build status accurately reflects code quality rather than environment configuration.

3. **As a developer running tests in the SA conda environment**, I want all 11 billing tests to continue executing and passing as before, so that the fix introduces no behavioral change in the intended runtime.

---

## Flow

```
pytest collects tests/test_billing.py
          |
          v
pytest.importorskip("pydantic_settings") executed
          |
     installed?
    /           \
  YES            NO
   |              |
   v              v
continue       SKIP entire module
   |           (reason printed, 0 failures)
   v
pytest.importorskip("fastapi") executed
          |
     installed?
    /           \
  YES            NO
   |              |
   v              v
continue       SKIP entire module
   |           (reason printed, 0 failures)
   v
All app imports proceed normally
   |
   v
11 tests execute and pass (SA env)
```

---

## Modules

| File | Change | Details |
|---|---|---|
| `tests/test_billing.py` | Insert two `pytest.importorskip` guards | After the `sys.path` setup block and before any `app.*` imports, add: `pydantic_settings = pytest.importorskip("pydantic_settings", reason="web backend deps not installed; run under SA conda env")` and `fastapi = pytest.importorskip("fastapi", reason="web backend deps not installed; run under SA conda env")` |
| `web_app/backend/requirements.txt` | No change | File is correct as-is; documents SA env deps |
| `requirements.txt` | No change | Must NOT add fastapi/pydantic-settings; would pollute base env |
| `requirements-optional.txt` | No change | Not appropriate for mandatory web backend deps |

---

## Acceptance

- [ ] Running `pytest tests/test_billing.py -v` in the base Python environment produces **0 failures and 11 skips** with skip reason containing "web backend deps not installed".
- [ ] Running `PYTHONPATH=web_app/backend /c/Users/naren/anaconda3/envs/SA/python.exe -m pytest tests/test_billing.py -v` in the SA conda environment produces **11 passed and 0 skips**.
- [ ] No new packages (`fastapi`, `pydantic-settings`, or any transitive dep) are added to `requirements.txt` or `requirements-optional.txt`.
- [ ] The full test suite run in the base env (`pytest` with no file filter) shows a net reduction of 11 errors/failures, replaced by 11 skips, with no other test counts changed.
- [ ] `pytest --tb=short` output in the base env contains no `ModuleNotFoundError` or `ImportError` tracebacks related to `pydantic_settings` or `fastapi`.
- [ ] The two `pytest.importorskip` lines appear before any `from app.` or `import app.` statement in `tests/test_billing.py`.

---

## Metrics

| Metric | Before Fix (base env) | After Fix (base env) | After Fix (SA env) |
|---|---|---|---|
| Billing test failures | 11 | 0 | 0 |
| Billing test skips | 0 | 11 | 0 |
| Billing tests passing | 0 | 0 | 11 |
| Import errors surfaced | 2 (`pydantic_settings`, `fastapi`) | 0 | 0 |
| Extra packages installed in base env | 0 | 0 | 0 (no change) |
| Developer triage time per false failure | ~5–10 min | 0 min | N/A |
| Lines of code changed | — | +2 lines in 1 file | — |
