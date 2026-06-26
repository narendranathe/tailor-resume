"""
create_prd_issues.py
Creates GitHub issues for new PRDs that don't yet have issues:
  - prd_education_parser.md   (Issue #129 tracking)
  - prd_fix_billing_web_deps.md
  - prd_fix_deployment_readiness_deps.md
  - prd_fix_remaining_parser_bugs.md
  - prd_ats_99.md             (if not already filed)

Usage:
    pip install PyGithub
    GITHUB_TOKEN=<your-token> python scripts/create_prd_issues.py

Or with gh CLI (must be authenticated):
    python scripts/create_prd_issues.py --use-gh
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from typing import List

REPO = "narendranathe/tailor-resume"


@dataclass
class Issue:
    title: str
    body: str
    labels: List[str]


ISSUES: List[Issue] = [
    # -------------------------------------------------------------------------
    # prd_education_parser.md — already implemented, track as closed reference
    # -------------------------------------------------------------------------
    Issue(
        title="feat(parsing): education single-line parser -- Issue #129 (PRD)",
        body="""\
## Problem

The education parser in `parsers/plain_parser.py` operates one field per line.
Modern resumes -- especially those exported from LinkedIn, Word, or populated from
LaTeX templates -- frequently condense a degree to a single line:

```
Missouri S&T -- M.S. Information Science | GPA: 4.0 | Jan 2022 - Dec 2023
```

When this line hits the current parser, only the institution or degree name is
extracted; GPA, dates, and sometimes the field of study are silently dropped.
The profile then has empty `dates` and `degree` fields, causing the renderer to
produce a malformed Education section.

**Root cause:** The parser checks `is_inst` and `is_degree` as independent boolean
flags and handles them in separate branches -- there is no path for "all on one line."

See full spec: `specs/prd_education_parser.md`

## Acceptance Criteria

- `"Missouri S&T -- M.S. Information Science | GPA: 4.0 | Jan 2022 - Dec 2023"`
  -> `institution="Missouri S&T"`, `degree="M.S. Information Science (GPA: 4.0)"`,
     `dates="Jan 2022 - Dec 2023"`
- `"University of Texas  B.S. Computer Science  2018 - 2022"` (double-space)
  -> institution, degree, dates all populated
- `"MIT  Ph.D. Machine Learning"` (no dates) -> institution and degree populated,
  dates empty string
- Multi-line education input (Jake template) -> unchanged behavior
- Bare date line `"Jan 2022 - Dec 2023"` -> not matched by one-liner, falls through
- All existing tests still pass (929 now pass; 7 new education tests added)

**Status:** Implemented. PRD reference issue for #129.
""",
        labels=["prd", "enhancement", "parsing"],
    ),

    # -------------------------------------------------------------------------
    # prd_fix_billing_web_deps.md
    # -------------------------------------------------------------------------
    Issue(
        title="fix: billing/web backend test skip guards for optional deps",
        body="""\
## Problem

The billing test suite (`tests/test_billing.py`) fails with 11 errors in the
base/default Python environment because `pydantic_settings` and `fastapi` are
listed in `web_app/backend/requirements.txt` but are absent from the root
`requirements.txt` and `requirements-optional.txt`. When pytest collects the
module, two chained `ModuleNotFoundError` exceptions abort import entirely:

- First error: `app.config` imports `pydantic_settings` -> 8 test failures
- Second error: `app.middleware.usage` imports `fastapi` -> 3 `TestSQLiteUsageStore` failures

CLAUDE.md documents that billing tests must run under the `SA` conda environment,
yet nothing in the test file enforces or communicates this boundary. Every developer
running `pytest` in the base env sees 11 loud failures that are not real regressions.

See full spec: `specs/prd_fix_billing_web_deps.md`

## Acceptance Criteria

- `pytest tests/test_billing.py -v` in base Python env produces **0 failures and
  11 skips** with skip reason containing "web backend deps not installed".
- `PYTHONPATH=web_app/backend <SA python> -m pytest tests/test_billing.py -v`
  in the SA conda env produces **11 passed and 0 skips**.
- No new packages (`fastapi`, `pydantic-settings`) added to `requirements.txt`
  or `requirements-optional.txt`.
- Full test suite in base env shows net reduction of 11 errors -> 11 skips,
  no other test counts changed.
- Two `pytest.importorskip` lines appear before any `from app.` imports in
  `tests/test_billing.py`.

## Fix

Insert in `tests/test_billing.py` after the `sys.path` setup block:

```python
pydantic_settings = pytest.importorskip(
    "pydantic_settings",
    reason="web backend deps not installed; run under SA conda env",
)
fastapi = pytest.importorskip(
    "fastapi",
    reason="web backend deps not installed; run under SA conda env",
)
```
""",
        labels=["prd", "bug"],
    ),

    # -------------------------------------------------------------------------
    # prd_fix_deployment_readiness_deps.md
    # -------------------------------------------------------------------------
    Issue(
        title="fix: pdfminer.six install + deployment readiness test",
        body="""\
## Problem

`pdfminer.six>=20221105` is declared as a critical dependency in `requirements.txt`
(line 17), but it is not present in the local Python 3.13 environment. The dependency
was silently dropped during installation because `pdfminer.six`'s `cffi`/`cryptography`
native extension stack has known wheel-build failures on Python 3.13.

Consequence: `TestRealEnvironment::test_critical_deps_installed_in_test_env` -- a
live-environment smoke check that asserts no critical imports are missing -- fails
with an `ImportError` on `import pdfminer`.

> **Warning:** Do NOT mark the test as skipped or xfail.
> `test_critical_deps_installed_in_test_env` is a mandatory CI sentinel.
> The fix must be an installation fix, not a test fix.

See full spec: `specs/prd_fix_deployment_readiness_deps.md`

## Acceptance Criteria

- `python -c "import pdfminer"` exits with code 0 and no output.
- `pytest tests/test_check_deployment_readiness.py::TestRealEnvironment::test_critical_deps_installed_in_test_env -v`
  reports `PASSED`.
- `pytest tests/test_check_deployment_readiness.py -v` reports 16 passed, 0 failed,
  0 skipped.
- `git diff tests/test_check_deployment_readiness.py` is empty -- sentinel test
  file is unchanged.
- If fix required switching to Python 3.11: `python --version` reports `Python 3.11.x`,
  matching `runtime.txt`.
- `pip check` reports no dependency conflicts after installation.

## Fix Flow

1. Attempt `pip install pdfminer.six` directly.
2. If that fails (cffi/cryptography build error on Python 3.13), switch to Python 3.11
   (matches `runtime.txt` / Streamlit Cloud target), recreate venv, reinstall deps.
3. Verify with `pytest tests/test_check_deployment_readiness.py -v`.
""",
        labels=["prd", "bug"],
    ),

    # -------------------------------------------------------------------------
    # prd_fix_remaining_parser_bugs.md
    # -------------------------------------------------------------------------
    Issue(
        title="fix(parser): remaining education one-liner edge cases",
        body="""\
## Problem

`_parse_education_oneliner` in `parsers/plain_parser.py` has two defects that
silently produce wrong structured output:

**Bug 1 (HIGH) -- bare 4-digit year not classified as a date.**
The token-classification loop tests each pipe-delimited token against `_DATE_PATTERN`,
which requires a month name, Q-prefix, YYYY-YYYY range, MM/YYYY slash, or YYYY-MM
hyphen. A standalone year like `2018` matches none of those, falls through to
`deg_parts.append(p)`, and contaminates the degree string.

Input: `"Ecole Polytechnique | M.Sc. Applied Math | 2018"`
Output: `degree='M.Sc. Applied Math 2018'` with empty `dates` field. (WRONG)

**Bug 2 (MEDIUM) -- ASCII hyphen-minus used as institution-degree separator is
not a split boundary.**
Strategy 1 splits only on pipe `|` and em-dash. A space-hyphen-space between
institution and degree is not split, so the first token becomes
`"May University - B.S. Biology"`, assigned entirely to `inst`; `deg` is empty;
function returns `None`.

Together these bugs cause incorrect or missing education fields in resumes that
use a standalone graduation year or a hyphen separator -- patterns common in
European and US academic CVs.

See full spec: `specs/prd_fix_remaining_parser_bugs.md`

## Acceptance Criteria

- `_parse_education_oneliner("Ecole Polytechnique | M.Sc. Applied Math | 2018")`
  returns `{'degree': 'M.Sc. Applied Math', 'dates': '2018'}` -- year not in degree.
- `_parse_education_oneliner("May University - B.S. Biology | 2018-2022")`
  returns non-`None` with `institution='May University'`, `degree='B.S. Biology'`,
  `dates='2018-2022'`.
- `pytest` reports **56 passed, 0 failed** (54 pre-existing + 2 new regression tests).
- `_parse_education_oneliner("Missouri S&T - Rolla | Electrical Eng | 2020")`
  correctly assigns `institution='Missouri S&T - Rolla'` (no false split on internal
  hyphen).
- Only `_parse_education_oneliner` is modified in `plain_parser.py`.

## Code Sketch

```python
# Fix 1 -- bare year (add after _DATE_PATTERN branch fails)
elif re.fullmatch(r'\\d{4}', p) and not dates:
    dates = p

# Fix 2 -- hyphen separator (after inst = raw_parts[0])
_m = re.search(r'\\s+-\\s+', inst)
if _m and _DEGREE_FIRST_RE.search(inst[_m.end():]):
    mid_parts.insert(0, inst[_m.end():])
    inst = inst[:_m.start()]
```
""",
        labels=["prd", "bug", "parsing"],
    ),

    # -------------------------------------------------------------------------
    # prd_ats_99.md -- check for duplicates before creating
    # -------------------------------------------------------------------------
    Issue(
        title="PRD: ATS 99+ scoring improvements (prd_ats_99.md)",
        body="""\
## Problem

A parallel audit of `jd_gap_analyzer.py`, `star_validator.py`, `latex_renderer.py`,
`text_utils.py`, and `pipeline.py` found 15 concrete bugs and gaps that prevent any
resume from scoring 99+ ATS -- even a perfectly-written one.

### Critical blockers

1. **`int()` truncation instead of `round()`** -- a formula result of 0.999 becomes
   99, not 100. Max achievable score is 99.
2. **3-char token filter drops key keywords** -- "sql", "etl", "dag", "ml", "ai"
   silently excluded from keyword overlap.
3. **Summary section commented out in LaTeX template** -- no generated resume ever
   includes a summary, eliminating the primary keyword-dense section ATS parsers
   weight most heavily.
4. **Bullet quality defaults to 0.0 for plain-text inputs** -- 20% quality
   component is always zero for plain-text resumes, capping ATS at 80.

See full spec: `specs/prd_ats_99.md` for all 15 fixes.

## Acceptance Criteria (must-pass)

- `round()` not `int()` in `estimate_ats_score()` -- raw value 0.999 returns 100.
- "sql", "etl", "dag" appear in keyword overlap when present in both JD and resume.
- A resume rendered from a profile with non-empty `summary` field includes a
  `Summary` section in the PDF.
- A plain-text resume blob produces a non-zero bullet quality score.
- Full test suite passes with 0 failures (excluding billing/web/api tests requiring
  SA env).

## Build Order

Fix 1 (round) -> Fix 2 (token filter) -> Fix 3 (summary template) ->
Fix 4 (plain-text bullets) -> Fix 5 (ACTION_VERBS) -> Fix 6 (verb window) ->
Fix 7 (TOOL_VOCAB) -> Fix 8 (seniority) -> Fix 9 (recommendations) ->
Fix 10 (word boundary) -> Fix 11 (min_freq) -> Fix 12 (metrics patterns) ->
Fix 13 (GitHub URL) -> Fix 14 (word-count penalty)
""",
        labels=["prd", "enhancement", "ats-score"],
    ),
]


def create_via_api(token: str) -> None:
    try:
        from github import Auth, Github
    except ImportError:
        print("PyGithub not installed. Run: pip install PyGithub")
        sys.exit(1)

    g = Github(auth=Auth.Token(token))
    repo = g.get_repo(REPO)

    # Ensure labels exist
    existing_labels = {lb.name for lb in repo.get_labels()}
    label_defs = {
        "prd": ("0075ca", "Product Requirements Document"),
        "ats-score": ("e4e669", "ATS scoring pipeline improvements"),
        "parsing": ("d93f0b", "PDF / plain-text parsing"),
        "enhancement": ("a2eeef", "New feature or request"),
        "bug": ("d73a4a", "Something is broken"),
    }
    for name, (color, desc) in label_defs.items():
        if name not in existing_labels:
            repo.create_label(name, color, desc)
            safe = name.encode("ascii", "replace").decode()
            print(f"  Created label: {safe}")
        else:
            safe = name.encode("ascii", "replace").decode()
            print(f"  Label exists:  {safe}")

    # Collect all open issue titles to detect duplicates
    existing_titles = {i.title for i in repo.get_issues(state="open")}

    created = []
    skipped = []
    for issue in ISSUES:
        if issue.title in existing_titles:
            safe = issue.title.encode("ascii", "replace").decode()
            skipped.append(safe)
            print(f"  SKIP (exists): {safe}")
            continue
        result = repo.create_issue(
            title=issue.title,
            body=issue.body,
            labels=issue.labels,
        )
        safe_title = issue.title.encode("ascii", "replace").decode()
        created.append((result.number, safe_title))
        print(f"  #{result.number}: {safe_title}")

    print()
    print(f"Done. {len(created)} created, {len(skipped)} skipped.")


def create_via_gh() -> None:
    for issue in ISSUES:
        label_str = ",".join(issue.labels)
        cmd = [
            "gh", "issue", "create",
            "--title", issue.title,
            "--body", issue.body,
            "--label", label_str,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            url = result.stdout.strip()
            safe = issue.title.encode("ascii", "replace").decode()
            print(f"  Created ({safe}): {url}")
        else:
            safe = issue.title.encode("ascii", "replace").decode()
            print(f"  Error ({safe}): {result.stderr.strip()}")


if __name__ == "__main__":
    use_gh = "--use-gh" in sys.argv

    if use_gh:
        print("Creating issues via gh CLI...")
        create_via_gh()
        sys.exit(0)

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("GITHUB_TOKEN not set and --use-gh not passed.")
        print()
        print("To run:")
        print("  GITHUB_TOKEN=<token> python scripts/create_prd_issues.py")
        print("  -- or --")
        print("  python scripts/create_prd_issues.py --use-gh   (requires: gh auth login)")
        print()
        print("Issues that will be created:")
        for i, issue in enumerate(ISSUES, 1):
            safe = issue.title.encode("ascii", "replace").decode()
            print(f"  {i}. {safe}  [{', '.join(issue.labels)}]")
        sys.exit(0)

    print("Creating issues via GitHub API...")
    create_via_api(token)
