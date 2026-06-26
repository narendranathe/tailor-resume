# PRD: Install pdfminer.six in local dev environment (Python 3.13 wheel-build workaround)

**Category:** deployment-readiness-deps
**Effort:** trivial
**Priority:** P2 — Blocking CI sentinel
**Date:** 2026-06-26
**Owner:** Platform / DevEx

---

## Problem

`pdfminer.six>=20221105` is declared as a critical dependency in `requirements.txt` (line 17), but it is not present in the local Python 3.13 environment. **The dependency was silently dropped during installation** because `pdfminer.six`'s `cffi`/`cryptography` native extension stack has known wheel-build failures on Python 3.13 — a fact already documented in comments inside `requirements.txt` itself. The environment either never ran `pip install -r requirements.txt` to completion, or the package was quietly excluded when the build aborted. `pypdf v6.14.2` is installed and working. The consequence is that `TestRealEnvironment::test_critical_deps_installed_in_test_env` — an intentional live-environment smoke check that calls the real `check_all()` function and asserts no critical imports are missing — fails with an `ImportError` on `import pdfminer`. This sentinel test exists precisely to catch `requirements.txt` drift; a failing sentinel blocks developer confidence and CI pipelines without surfacing any actionable feedback about the feature under development. Adding a skip marker is explicitly ruled out: it would permanently silence the alarm the test was designed to raise.

> **Warning:** Do not mark the test as skipped or xfail. `test_critical_deps_installed_in_test_env` is a mandatory CI sentinel. Making it optional defeats its only purpose. The fix must be an installation fix, not a test fix.

---

## Users

| Persona | Role | How they're affected now | What they need |
|---|---|---|---|
| **Local developer** | Runs tests in a Python 3.13 venv | 1 unexplained test failure blocks a clean test run; no clear error message ties the failure to a missing wheel | `pip install pdfminer.six` succeeds, or a clear path to switch to Python 3.11 |
| **CI pipeline** | Automated build and test on every push | Pipeline exits non-zero; the failure looks like a product regression rather than an environment gap, muddying the signal | All 16 tests green; sentinel confirms the real environment matches `requirements.txt` |
| **Streamlit Cloud (deployment target)** | Runs the production app on Python 3.11 per `runtime.txt` | Unaffected today, but if local dev normalises around Python 3.13 without `pdfminer.six`, a production regression is one silent drift away | Local environment matches the production Python version so parity is preserved |
| **End user** | Uploads a PDF resume for tailoring | Not yet impacted; PDF parsing still works via `pypdf`, but if `pdfminer.six`-specific code paths are exercised the app will crash silently | All declared dependencies installed so the full feature surface is reachable |

---

## Stories

**US-1** — As a **developer**, I want `pip install -r requirements.txt` to install all declared dependencies without silent failures, so that my local environment reflects what is declared and I do not investigate phantom test failures.
_So that:_ `import pdfminer` succeeds and the deployment-readiness sentinel passes.

**US-2** — As a **CI pipeline**, I want the full test suite to exit 0 with all 16 tests passing, so that green CI reliably means "the app is deployable", not "the app minus its missing dependencies is deployable".
_So that:_ on-call engineers trust the CI signal and are not forced to cross-check dependency drift manually.

**US-3** — As a **project maintainer**, I want the local Python version to match the production Python version (3.11, per `runtime.txt`), so that wheel-build failures in dev do not hide production-only breakage and vice versa.
_So that:_ environment parity is enforced and `pdfminer.six` wheel builds are not a recurring problem.

---

## Flow

```
START: local env is Python 3.13, pdfminer.six missing
         │
         ▼
STEP 1 — Attempt direct install
  $ pip install pdfminer.six
         │
         ├─── SUCCESS ─────────────────────────────────────┐
         │    (pip finds a compatible wheel)                │
         │                                                  │
         └─── FAIL (cffi/cryptography build error on 3.13) │
                │                                           │
                ▼                                           │
STEP 2 — Switch runtime to Python 3.11                     │
  (matches runtime.txt, Streamlit Cloud target)             │
  $ pyenv install 3.11 / use pyenv local 3.11               │
  $ python -m venv .venv && source .venv/bin/activate        │
  $ pip install -r requirements.txt                          │
         │                                                   │
         ▼                                                   │
pdfminer.six installed ◄────────────────────────────────────┘
         │
         ▼
STEP 3 — Verify
  $ python -m pytest tests/test_check_deployment_readiness.py -v
         │
         ├─── 16/16 PASS → DONE
         │
         └─── FAIL on other tests → investigate separately
                (all 15 other tests already pass; scope is narrow)
```

---

## Modules

| File | Change type | Exact change |
|---|---|---|
| `requirements.txt` | no edit needed | Line 17 already declares `pdfminer.six>=20221105` correctly. No edit required. Installation, not the file, is the fix. |
| `tests/test_check_deployment_readiness.py` | no edit needed | The failing test `TestRealEnvironment::test_critical_deps_installed_in_test_env` must not be modified. It is a CI sentinel and must remain strict. |
| `runtime.txt` (read-only, reference) | reference | Confirms Python 3.11 is the target runtime for Streamlit Cloud. Use this to justify the Python version switch if Step 1 fails. |
| `README.md` / `CONTRIBUTING.md` (if present) | optional update | Add a note: "This project requires Python 3.11 (see `runtime.txt`). `pdfminer.six` wheel builds fail on Python 3.13 due to `cffi` incompatibility." Prevents the next developer hitting the same wall. |

---

## Acceptance

- [ ] **AC-1 (import resolves):** Running `python -c "import pdfminer"` in the active virtual environment exits with code 0 and no output.
- [ ] **AC-2 (sentinel passes):** `pytest tests/test_check_deployment_readiness.py::TestRealEnvironment::test_critical_deps_installed_in_test_env -v` reports `PASSED`.
- [ ] **AC-3 (full suite green):** `pytest tests/test_check_deployment_readiness.py -v` reports 16 passed, 0 failed, 0 skipped.
- [ ] **AC-4 (no test modified):** `git diff tests/test_check_deployment_readiness.py` is empty — the sentinel test file is unchanged.
- [ ] **AC-5 (version parity, conditional):** If the fix required switching to Python 3.11, `python --version` reports `Python 3.11.x`, matching `runtime.txt`.
- [ ] **AC-6 (no requirements drift):** `pip check` reports no dependency conflicts in the environment after installation.

---

## Metrics

| Metric | Before | After | Source of truth |
|---|---|---|---|
| Failing tests in suite | **1 / 16** | **0 / 16** | `pytest --tb=short` exit code |
| Passing tests in suite | 15 / 16 | 16 / 16 | `pytest -v` summary line |
| Critical deps missing (check_all) | 1 (`pdfminer`) | 0 | `python -c "from check_deployment_readiness import check_all; print(check_all())"` |
| CI exit code | 1 (non-zero) | 0 | CI run log |
| Time-to-fix (estimated) | — | < 5 min (install) or < 20 min (runtime switch + reinstall) | Manual timing |
| Runtime version match to production | 3.13 (mismatch) | 3.11 (match) | `python --version` vs `runtime.txt` |
