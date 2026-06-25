# PRD: Education Single-Line Parsing

**Pipeline:** Problem → Users → Stories → Flow → Modules → Acceptance → Metrics
**GitHub Issue:** #129
**Status:** Implemented

---

## Problem

The education parser in `parsers/plain_parser.py` (lines 409–422) operates one field per line.
Modern resumes — especially those exported from LinkedIn, Word, or populated from LaTeX templates —
frequently condense a degree to a single line:

```
Missouri S&T — M.S. Information Science | GPA: 4.0 | Jan 2022 – Dec 2023
```

When this line hits the current parser, only the institution or degree name is extracted;
GPA, dates, and sometimes the field of study are silently dropped. The profile then has
empty `dates` and `degree` fields, causing the renderer to produce a malformed Education section.

**Root cause:** The parser checks `is_inst` and `is_degree` as independent boolean flags and handles
them in separate branches — there is no path for "all on one line."

**Cost of inaction:** Every user whose education fits on one line (LinkedIn export users, DOCX users,
anyone who hasn't hand-formatted their resume for multi-line parsing) gets an incomplete Education
section, lowering their rendered resume quality with no error or warning.

---

## Target Users

| Persona | Resume source | Impact |
|---|---|---|
| LinkedIn export user | LinkedIn PDF → `parse_pdf()` → one-liner education | GPA and dates lost |
| DOCX user | Word template condensed to one line | Degree field partially parsed |
| Jake-template LaTeX user | Multi-line (not affected — already works) | No change |
| Plain-blob paster | Mixed format, could be either | Single-line path now helps |

---

## User Stories

1. As a user whose LinkedIn PDF exports education as a single condensed line, I want my GPA,
   degree, and dates all parsed correctly so the rendered Education section matches my resume.

2. As a user who manually pastes a resume blob, I want `parse_blob` to correctly extract
   `M.S. Information Science, GPA: 4.0, Jan 2022 – Dec 2023` from one line without reformatting.

3. As a developer debugging a parsing failure, I want the parser to try the single-line path first,
   then fall back to the current multi-line path, so the code is explicit about which path ran.

---

## Flow

```
education section line arrives
        ↓
Try _parse_education_oneliner(line)
        ↓
  match? ──yes──→  extract institution, degree, GPA, dates → append to profile.education
        ↓ no
Existing multi-line heuristics (is_inst, is_degree, date_m branches)
```

No change to the multi-line path — purely additive. The one-liner regex runs first and
short-circuits only when it matches.

---

## Modules

**File: `parsers/plain_parser.py`**

New function `_parse_education_oneliner(line: str) -> Optional[Dict]`:

Strategy (ordered by specificity):
1. `Institution SEPARATOR Degree [| GPA] [| Dates]` — pipe/dash delimited
2. `Institution  Degree  Dates` — double-space delimited (fallback)
3. Fall through → `None` → existing parser runs unchanged

Fields extracted: `institution`, `degree` (includes GPA as suffix when present), `dates`, `location`.

Integration: called at the top of the `elif section == "education":` block. When it returns a dict,
append and `continue`; otherwise fall through to existing logic.

---

## Acceptance Criteria

- [x] `"Missouri S&T — M.S. Information Science | GPA: 4.0 | Jan 2022 – Dec 2023"` →
      `institution="Missouri S&T"`, `degree="M.S. Information Science (GPA: 4.0)"`, `dates="Jan 2022 – Dec 2023"`
- [x] `"University of Texas  B.S. Computer Science  2018 – 2022"` (double-space) →
      institution, degree, dates all populated
- [x] `"MIT  Ph.D. Machine Learning"` (no dates) → institution and degree populated, dates empty string
- [x] Multi-line education input (Jake template) → unchanged behavior (existing path still fires)
- [x] Bare date line `"Jan 2022 – Dec 2023"` → not matched by one-liner, falls through
- [x] All 907 existing tests still pass (929 now pass; 7 new education tests added)

---

## Metrics

| Metric | Before | Target |
|---|---|---|
| Education fields populated for single-line inputs | ~30% (institution only) | 90%+ |
| Tests covering single-line education | 0 | ≥ 5 |
| Regression in existing tests | — | 0 |
