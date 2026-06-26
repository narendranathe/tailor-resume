# PRD — Fix Education Parser: Bare-Year Date Classification and Hyphen Institution–Degree Separator

**ID:** PRD-parser-002  
**Category:** remaining-parser-bugs  
**Effort:** Small  
**Status:** Ready for dev  
**Date:** 2026-06-26

---

## 01 — Problem

`_parse_education_oneliner` in `.claude/skills/tailor-resume/scripts/parsers/plain_parser.py` harbours two defects that silently produce wrong structured output rather than raising an error, making them invisible to casual inspection.

**Bug 1 (HIGH) — bare 4-digit year not classified as a date.** The token-classification loop tests each pipe-delimited token against `_DATE_PATTERN`, which requires a month name, Q-prefix, YYYY–YYYY range, MM/YYYY slash, or YYYY-MM hyphen. A standalone year like `2018` matches none of those, falls through to `deg_parts.append(p)`, and contaminates the degree string. Input `"Ecole Polytechnique | M.Sc. Applied Math | 2018"` yields `degree='M.Sc. Applied Math 2018'` with an empty `dates` field.

**Bug 2 (MEDIUM) — ASCII hyphen-minus used as institution–degree separator is not a split boundary.** Strategy 1 splits only on pipe `|` and em-dash `—` (line 195). A space-hyphen-space between institution and degree is not split, so the first token becomes `"May University - B.S. Biology"`, which is assigned entirely to `inst`; `deg` is empty; the function returns `None`. The fallback heuristic then stores the raw line as the institution with blank degree and dates.

Together these bugs cause incorrect or missing education fields in any resume that uses a standalone graduation year or a hyphen separator — patterns common in European and US academic CVs. Downstream tailoring logic that relies on the `dates` or `degree` fields produces incorrect output silently, costing developer debugging time and producing wrong artifacts for end users.

---

## 02 — Users

| Persona | Role in system | How the bug hits them | Severity |
|---|---|---|---|
| Resume owner / end user | Submits plain-text resume; receives tailored PDF | Graduation year merged into degree string; wrong or empty dates field in output document | HIGH |
| Skills developer | Maintains and extends `plain_parser.py` | Silent wrong output; must trace through token-classification logic to diagnose; no exception raised to guide them | MEDIUM |
| CI pipeline / test suite | Runs 54 automated parser tests on every commit | Two test cases fail; build is red; other PRs blocked until fix lands | HIGH |
| ATS / downstream consumer | Ingests structured education data from parser output | Date field missing or degree field carrying spurious year token; may mis-rank or reject candidate record | MEDIUM |

---

## 03 — User Stories

**Story 1 — End user (bare year)**  
As a resume owner who writes my education as `"Ecole Polytechnique | M.Sc. Applied Math | 2018"`, I want the parser to recognise `2018` as a graduation year so that my tailored resume shows the correct dates and a clean degree title — not `"M.Sc. Applied Math 2018"`.  
_Acceptance: `_parse_education_oneliner(…)` returns `{'degree': 'M.Sc. Applied Math', 'dates': '2018', …}`._

**Story 2 — End user (hyphen separator)**  
As a resume owner who writes `"May University - B.S. Biology | 2018-2022"`, I want the parser to split on the space-hyphen-space separator so that institution, degree, and dates are each correctly extracted — not collapsed into a single institution field.  
_Acceptance: returns `{'institution': 'May University', 'degree': 'B.S. Biology', 'dates': '2018-2022'}` and no `None`._

**Story 3 — Developer**  
As a developer maintaining `plain_parser.py`, I want both fixes to be contained within `_parse_education_oneliner` with no schema changes so that all 54 existing tests continue to pass and I can verify correctness at a glance.  
_Acceptance: `pytest tests/test_plain_parser.py` reports 56 passed, 0 failed._

---

## 04 — Fix Flow

```
Input line (raw education string)
     │
     ▼
┌─────────────────────────────────────────────────────┐
│  Strategy 1: pipe / em-dash split  (line ~195)      │
│                                                     │
│  NEW → after extracting inst from raw_parts[0],     │
│        check if inst contains a recognised degree   │
│        marker (_DEGREE_FIRST_RE) separated by ' - ' │
│        If so, split inst further → inst + deg_parts │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│  Token-classification loop  (line ~257)             │
│                                                     │
│  for each token p:                                  │
│    if _DATE_PATTERN.search(p)  → dates              │
│    NEW → elif re.fullmatch(r'\d{4}', p)             │
│              and not dates      → dates             │
│    else                         → deg_parts         │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│  Assemble result dict                               │
│   institution, degree (joined deg_parts), dates     │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
Return parsed education dict  (no None, no contaminated fields)
```

---

## 05 — Modules

| File | Location | Change | Bug fixed |
|---|---|---|---|
| `.claude/skills/tailor-resume/scripts/parsers/plain_parser.py` | Line ~257, `_parse_education_oneliner` token-classification loop | After the `_DATE_PATTERN.search(p)` branch fails, add: `elif re.fullmatch(r'\d{4}', p) and not dates: dates = p`. Prevents bare 4-digit year tokens from appending to `deg_parts`. | Bug 1 |
| `.claude/skills/tailor-resume/scripts/parsers/plain_parser.py` | Line ~195, `_parse_education_oneliner` after `inst = raw_parts[0]` | After assigning `inst`, check whether `inst` matches `re.search(r'\s+-\s+', inst)` and the trailing portion matches `_DEGREE_FIRST_RE`. If so, split on the last ` - ` occurrence: reassign `inst` to the prefix and prepend the suffix into `mid_parts` as the degree token. Avoids false splits on legitimate hyphenated institution names. | Bug 2 |
| `tests/test_plain_parser.py` (or equivalent) | New test cases | Add two regression tests matching the failing-test specs: bare-year test for `"Ecole Polytechnique | M.Sc. Applied Math | 2018"` and hyphen-separator test for `"May University - B.S. Biology | 2018-2022"`. | Both |

No schema changes. No changes outside `_parse_education_oneliner` in the production file.

**Code sketch:**

```python
# Fix 1 — bare year (add after _DATE_PATTERN branch fails)
elif re.fullmatch(r'\d{4}', p) and not dates:
    dates = p

# Fix 2 — hyphen separator (after inst = raw_parts[0])
_m = re.search(r'\s+-\s+', inst)
if _m and _DEGREE_FIRST_RE.search(inst[_m.end():]):
    mid_parts.insert(0, inst[_m.end():])
    inst = inst[:_m.start()]
```

---

## 06 — Acceptance

- [ ] **Bare-year classification:** `_parse_education_oneliner("Ecole Polytechnique | M.Sc. Applied Math | 2018")` returns `{'degree': 'M.Sc. Applied Math', 'dates': '2018'}` — year does not appear in the degree string.
- [ ] **Hyphen separator parsing:** `_parse_education_oneliner("May University - B.S. Biology | 2018-2022")` returns a non-`None` dict with `institution='May University'`, `degree='B.S. Biology'`, and `dates='2018-2022'`.
- [ ] **Regression — all existing tests pass:** `pytest` reports **56 passed, 0 failed** (54 pre-existing + 2 new regression tests).
- [ ] **No false splits on hyphenated institution names:** `_parse_education_oneliner("Missouri S&T - Rolla | Electrical Eng | 2020")` correctly assigns `institution='Missouri S&T - Rolla'` without splitting on the internal hyphen (trailing portion does not match `_DEGREE_FIRST_RE`).
- [ ] **No schema changes required:** Output dict shape is unchanged; all keys (`institution`, `degree`, `dates`) remain identical to pre-fix contract.
- [ ] **Scope is contained:** Only `_parse_education_oneliner` is modified in `plain_parser.py`; no other functions have diffs.

---

## 07 — Metrics

| Metric | Before fix | After fix | Delta |
|---|---|---|---|
| Test suite — passing | 54 | 56 | +2 |
| Test suite — failing | 2 | 0 | −2 (green build) |
| Bare-year inputs producing correct `dates` | 0% | 100% | +100 pp |
| Hyphen-separator inputs returning a parsed dict | 0% | 100% | +100 pp |
| Lines changed in production file | — | ≤ 8 | Small / contained |
| Schema changes | — | 0 | No breaking change |
| Functions modified | — | 1 (`_parse_education_oneliner`) | Minimal blast radius |
| CI build status | Red | Green | Unblocked |
