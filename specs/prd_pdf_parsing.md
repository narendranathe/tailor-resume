# PRD: PDF Parsing Accuracy — Regex-First Pipeline

> Product-Driven Development pipeline: **Problem → Users → Stories → Flow → Modules → Acceptance → Metrics**.
> All architectural decisions made here will be appended to `specs/README.md` upon implementation.

---

## Overview

The PDF parsing pipeline (`pdf_extractor.py` + `plain_parser.py`) misidentifies dates as role titles, drops project bullets, reverses column order, and injects spurious bullet characters. The fixes are regex-based and deterministic — zero Claude calls required for correctly-formatted PDFs. This PRD specifies the four critical bug fixes and six structural improvements that raise parse accuracy to parity with the LaTeX and Markdown paths.

## Problem Statement

Three concrete failure modes occur on every Jake-template LaTeX PDF:

1. **Column reconstruction is backwards.** `_extract_pdf_text_pdfminer` outputs the right column (date pool) before the left column (content), then stops early because the `break` inside the gap-finder exits before measuring the actual column gap. Downstream, the plain parser sees dates before role titles and produces garbage.
2. **Orphaned bullets are silently dropped.** When pdfminer reads in column order, project bullets arrive before the project header. Without a stash, they vanish. (Issue #115, fixed in the last session; this PRD addresses the upstream extraction root cause.)
3. **`_box_lines` injects fake bullets.** Any text box with two sentences gets a `"• "` prefix — turning continuous prose (like a school name + degree on two lines) into fabricated bullets.

Cost of inaction: every uploaded Jake-template PDF produces a mangled profile. Users receive an ATS-scored resume tailored to the wrong bullets. The Claude fallback masks the problem but costs $0.10/call for data that regex can parse in milliseconds.

## Target Users (Primary)

| Persona | Description | Impact |
|---|---|---|
| **Job seeker uploading a LaTeX PDF** | Has a Jake-template PDF from Overleaf or a local `pdflatex` compile. | High — this is the primary artifact format for the product's target users (technical/engineering candidates). |
| **Narendra (dog-fooding)** | Uses `Naren_citi.pdf` and similar resumes daily. Every parse error is immediate friction. | High — all development is dog-food driven. |
| **Returning user with vault** | Relies on consistent re-parse to retrieve old resume versions. | Medium — parse instability breaks vault identity. |

## User Stories

1. **As a user uploading a Jake-template PDF**, dates should appear on each role header — not pooled at the top of the profile as phantom role titles, so my experience section reflects my actual work history.
2. **As a user**, project bullets should be attached to the correct project — not silently dropped — so the Projects section is complete.
3. **As a user**, bullet text should not appear in my company name or project title fields, so I don't have to manually fix a garbled profile after upload.
4. **As a user**, uploading a PDF should not trigger a Claude API call when the PDF is clean and parseable by pdfminer.six, so I don't waste API credits on deterministic work.
5. **As Narendra**, running the test suite after a parser change should give me confidence that fixes don't regress Fixture A (reading-order) or Fixture B (column-disordered) text, so I can ship without manual spot-checks.

## Detailed Flow

### Current (broken) parse path for Jake-template PDFs

```
PDF bytes
  → pdfminer.six (LAParams: boxes_flow=0.5, line_margin=0.3)
    → _extract_pdf_text_pdfminer()
        ├── x0 gap finder: BREAKS EARLY (BUG 1) → split_x not computed
        ├── column output: RIGHT before LEFT (BUG 2) → dates precede content
        └── _box_lines: injects "• " on multi-sentence boxes (BUG 3)
  → _normalize_ot1_artifacts()
  → _parse_plain_resume_text()
      ├── date lines treated as role titles (downstream of BUG 1+2)
      └── bullets arrive before project header → dropped (downstream of BUG 1+2)
```

### Fixed parse path

```
PDF bytes
  → pdfminer.six (LAParams: boxes_flow=None, line_margin=0.5)  [Fix 4]
    → _extract_pdf_text_pdfminer()
        ├── x0 gap finder: full scan, threshold 50pt  [Fix 1]
        ├── column output: LEFT before RIGHT  [Fix 2]
        └── _box_lines: no spurious bullets  [Fix 3]
  → _normalize_ot1_artifacts()
  → _parse_plain_resume_text()
      └── correct reading order → roles, bullets, projects parsed cleanly
```

### Module 1 — `pdf_extractor.py`: column gap finder (Fix 1)

**Bug:** `if x0_vals[i + 1] > page_mid: break` exits the loop before the 272pt gap between left and right columns is measured.

**Fix:** Remove the `break`. Scan all adjacent pairs and keep the largest gap regardless of position. Raise the minimum threshold from 15pt to 50pt (eliminates margin jitter false positives while reliably detecting the 272pt two-column gap on 8.5" pages).

```python
# Before (broken)
for i in range(len(x0_vals) - 1):
    if x0_vals[i + 1] > page_mid:
        break
    gap = x0_vals[i + 1] - x0_vals[i]
    if gap > max_gap:
        max_gap, best_i = gap, i
if max_gap > 15:
    split_x = ...

# After (fixed)
for i in range(len(x0_vals) - 1):
    gap = x0_vals[i + 1] - x0_vals[i]
    if gap > max_gap:
        max_gap, best_i = gap, i
if max_gap > 50:
    split_x = ...
```

### Module 2 — `pdf_extractor.py`: column reconstruction order (Fix 2)

**Bug:** Lines 564-570 emit `right` before `left`. For Jake-template PDFs the right column is the date pool; outputting it first means the plain parser sees dates before any role title.

**Fix:** Swap the output order — left column first, then a separator, then right column. The plain parser already handles orphan dates via `orphan_dates` stash, but correct ordering eliminates the need for the stash on well-formed PDFs.

```python
# After (fixed)
for _, _, text in left:
    parts.extend(_box_lines(text))
parts.append("")
for _, _, text in right:
    parts.extend(_box_lines(text))
```

### Module 3 — `pdf_extractor.py`: spurious bullet injection in `_box_lines` (Fix 3)

**Bug:** `_box_lines` calls `_split_bullet_block` which splits on sentence boundaries, then prefixes every sentence with `"• "`. A degree line like `"Master of Science in Information Science\nGPA: 4.0/4.0"` becomes two fake bullets.

**Fix:** Only split on explicit bullet characters (`•`, `-`, `–` at line start). Never inject `"• "` programmatically. Return raw lines from `text.split("\n")`.

```python
# After (fixed)
def _box_lines(text: str) -> List[str]:
    return [ln.strip() for ln in text.split("\n") if ln.strip()]
```

### Module 4 — `pdf_extractor.py`: LAParams tuning (Fix 4)

**Current:** `LAParams(char_margin=1.5, line_margin=0.3, word_margin=0.05, boxes_flow=0.5)`

- `boxes_flow=0.5` causes pdfminer to mix horizontal and vertical proximity when grouping characters into boxes — columns bleed into each other.
- `line_margin=0.3` merges adjacent lines from different sections (e.g., company name + date pool) into a single box.

**Fix:**
```python
LAParams(char_margin=1.5, line_margin=0.5, word_margin=0.1, boxes_flow=None)
```
- `boxes_flow=None` disables flow analysis — boxes are strictly separated by coordinate gaps (correct for two-column layouts).
- `line_margin=0.5` gives more vertical space between logical groups, preventing cross-section merging.

### Module 5 — `plain_parser.py`: `_DATE_PATTERN` — add `to` separator (Fix 5)

**Bug:** Dates formatted as `"Jan 2021 to Dec 2022"` (common in LinkedIn and DOCX exports) are not matched. The pattern covers `–`, `—`, `/`, and `-` but not the word `to`.

**Fix:** Extend the separator alternation in `_DATE_PATTERN`:
```python
_SEP = r"(?:\s*(?:–|—|to|-|/|thru|through)\s*)"
```

### Module 6 — `plain_parser.py`: section header aliases (Fix 6)

**Bug:** `_SECTION_HEADERS` misses common ATS section names: `"Work Experience"`, `"Professional Experience"`, `"Employment History"`, `"Technical Projects"`, `"Personal Projects"`, `"Awards"`, `"Achievements"`, `"Certifications"`.

**Fix:** Extend the aliases dict:
```python
"experience": [..., "work experience", "professional experience", "employment history", "work history"],
"projects": [..., "technical projects", "personal projects", "side projects", "open source"],
"certifications": [..., "licenses", "awards", "achievements", "honors"],
```

## Acceptance Criteria

### Must-pass (blocking)

- [ ] `tests/test_plain_parser_jake_template.py::TestFixtureAOrderedText` — all 7 tests pass (no regression on reading-order text).
- [ ] `tests/test_plain_parser_jake_template.py::TestFixtureBDisorderedText` — all 8 tests pass (includes `test_fraud_pipeline_has_two_bullets` from #115).
- [ ] `python -m pytest tests/ -v --ignore=tests/test_billing.py --ignore=tests/test_web_api.py` — ≥ 349 tests pass, 0 failures.
- [ ] Column reconstruction: a Jake-template PDF produces `experience[0].start == "July 2024"` (not blank or a date-as-title).
- [ ] `_box_lines` never injects `"• "` into a text block that does not start with a bullet character.
- [ ] `split_x` is computed for two-column PDFs: the 272pt gap on a Letter page is found; `max_gap > 50` is satisfied.

### Should-pass (non-blocking but expected)

- [ ] `_DATE_PATTERN` matches `"Jan 2021 to Dec 2022"` in `TestDatePatternFirstMatch`.
- [ ] `_SECTION_HEADERS` maps `"Work Experience"` → `"experience"` in a new `TestSectionHeaders` test class.
- [ ] LAParams change does not break 5 pdfminer-dependent tests (they were SKIPPED due to missing library; still SKIP after the change if pdfminer is absent).

## Non-Functional Requirements

- **No new dependencies.** All fixes are pure Python; no libraries added to `requirements.txt`.
- **No Claude API calls triggered by regex-parseable PDFs.** The `_parse_with_claude` path is only reached when pdfminer produces an empty or too-short string (< 100 chars after strip).
- **Performance.** pdfminer extraction with the new LAParams must complete in < 5s for a standard 1-page resume on a 2022-era CPU.
- **No PII.** Fixture strings in tests use only the public resume content already in the test file.

## Module Breakdown

| Module | File | Fix | Complexity |
|---|---|---|---|
| 1 — Column gap finder | `pdf_extractor.py:540–551` | Remove `break`; raise threshold 15→50pt | XS |
| 2 — Column output order | `pdf_extractor.py:560–573` | Swap left/right emission order | XS |
| 3 — `_box_lines` | `pdf_extractor.py:553–557` | Remove `_split_bullet_block` call; return raw lines | XS |
| 4 — LAParams | `pdf_extractor.py:522` | `boxes_flow=None, line_margin=0.5, word_margin=0.1` | XS |
| 5 — `_DATE_PATTERN` | `plain_parser.py` (top-of-file) | Add `to|thru|through` to separator alternation | XS |
| 6 — Section aliases | `plain_parser.py:_SECTION_HEADERS` | 8 new alias strings across 3 sections | XS |

Build order: Fixes 4 → 1 → 2 → 3 (LAParams first so gap finder operates on correct boxes) → 5 → 6.

## Dependency Graph

```
LAParams (Fix 4)
    │
    ▼
Column gap finder (Fix 1) → split_x correct
    │
    ▼
Column output order (Fix 2) → left emitted before right
    │
    ▼
_box_lines (Fix 3) → no spurious bullets
    │
    ▼
_parse_plain_resume_text (existing)
    ├── _DATE_PATTERN (Fix 5) → "to" separator matched
    └── _SECTION_HEADERS (Fix 6) → wider alias coverage
```

## Out of Scope

- Multi-column resume layouts beyond 2-column (3-column grids are not produced by Jake template).
- Scanned / image-based PDFs (use Tier 0 Claude vision extraction — separate skill path).
- pypdf and stdlib fallback path improvements (they are reading-order and do not suffer from the column bug).
- DOCX column layout parsing (DOCX does not have the two-column coordinate problem).

## Open Questions

1. Should `_box_lines` preserve explicit bullet characters from the original PDF (e.g., a `•` already in the extracted text), or strip and re-emit them? **Recommend: preserve — pass raw lines through; let the plain parser detect `•` at line start.**
2. Should `boxes_flow=None` be the permanent default, or should it fall back to `0.5` for non-two-column PDFs? **Recommend: `None` always — the coordinate-based gap finder handles single-column PDFs correctly with `split_x = None`.**
3. Should the LAParams change and gap-finder change be shipped as a single commit or two? **Recommend: single commit — they are coupled (LAParams determines what boxes exist; gap finder depends on box coordinates).**

## Success Metrics (post-implementation)

| Metric | Target |
|---|---|
| Jake-template PDF parse pass rate (manual spot-check, 5 PDFs) | 5/5 correct role + date pairings |
| `TestFixtureB` tests passing | 8/8 |
| Claude API calls triggered per clean PDF upload | 0 |
| Total test suite failures after merge | 0 |
| Lines of code changed | < 30 (all 6 fixes are surgical) |

## Definition of Done

- [ ] All 6 module fixes implemented in the files listed above.
- [ ] `python -m pytest tests/ -v --ignore=tests/test_billing.py --ignore=tests/test_web_api.py` passes with 0 failures.
- [ ] `python -m ruff check .claude/skills/tailor-resume/scripts/ tests/` passes with 0 new violations.
- [ ] `python scripts/sync_global.py` propagates changes to `~/.claude/skills/tailor-resume/`.
- [ ] `specs/README.md` updated with a new date entry documenting the LAParams and gap-finder decisions.
- [ ] `UBIQUITOUS_LANGUAGE.md` extended with: **column gap finder**, **box_flow=None**, **split_x**, **orphan stash**.
- [ ] All new test assertions follow the existing `TestFixtureB` pattern (no mocking; use real `_parse_plain_resume_text` calls).
