# PRD — Plain Parser Sprint: Normalizer & Deduplication Fixes

## Problem

The plain-text resume parser (`parsers/plain_parser.py`) and its shared normalizer (`parsers/normalizer.py`) have three latent correctness issues that silently degrade profile quality downstream. First, `_dedupe()` in `normalizer.py` uses `dict.fromkeys()` which is case-sensitive, so "Python" and "python" both survive into the skills list and inflate keyword-overlap scores in the ATS scorer. Second, `_parse_dates()` returns raw date strings without normalization, causing ATS date comparison and LaTeX rendering to receive inconsistent formats like "07/2024", "2024-07", "July 2024", and "Jul 2024" for the same calendar month — the gap analyzer and test assertions cannot reliably compare them. Third, `profile_extractor.py` historically contained a divergent in-module copy of `_parse_plain_resume_text` that had fallen behind the bug fixes in `parsers/plain_parser.py` for issues #101–#104; while a thin delegate was already introduced, the divergent legacy body remains and callers not importing from the canonical location silently received the pre-fix parser. Without addressing these issues, ATS scores can be artificially inflated by duplicate skills, date-range gap calculations return wrong results, and any future regression in the delegate wiring would silently reactivate pre-fix parsing bugs.

## Users

| Persona | Resume source / entry point | Impact |
|---|---|---|
| Job seeker uploading PDF resume | `parse_pdf()` → `_parse_plain_resume_text()` | Duplicate skills inflate ATS score; inconsistent dates corrupt gap analysis |
| Job seeker pasting LinkedIn text | `parse_linkedin()` → `parse_blob()` | Skills from bullets may appear twice in different cases |
| Developer running regression tests | pytest test suite | Flaky assertions on date format; duplicate skills cause count mismatches |
| Pipeline operator using MCP tool | `execute_text()` via `mcp_server.py` | All issues above compound across async calls |

## User Stories

- As a job seeker, I want my skills list to be deduplicated case-insensitively so that "Python" and "python" do not appear as separate skills and inflate my ATS score.
- As a developer running tests, I want date strings to be normalized to "Mon YYYY" abbreviated format so that date assertions are deterministic regardless of input format (slash, ISO, or long month name).
- As a pipeline maintainer, I want `profile_extractor._parse_plain_resume_text` to always delegate to `parsers.plain_parser` so that any fix applied to the canonical parser is automatically picked up by all callers without code duplication.

## Flow

```
BEFORE:
  plain text → _parse_plain_resume_text (profile_extractor copy, pre-#101..104)
                        ↓
               normalizer._dedupe()  ← case-sensitive, "Python"+"python" survive
                        ↓
               normalizer._parse_dates() ← raw string "07/2024" returned as-is
                        ↓
               Profile with duplicate skills + inconsistent date strings

AFTER:
  plain text → profile_extractor._parse_plain_resume_text (thin delegate)
                        ↓
               parsers/plain_parser._parse_plain_resume_text (canonical, #101-#104 fixed)
                        ↓
               normalizer._dedupe()  ← case-insensitive, "Python" wins over "python"
                        ↓
               normalizer._parse_dates() ← normalizes to "Jul 2024" / "Present"
                        ↓
               Profile with clean skills + consistent date strings
```

## Modules

| File | Line range | Exact change description |
|---|---|---|
| `parsers/normalizer.py` | 16–18 | Replace `dict.fromkeys` in `_dedupe()` with case-insensitive seen-set loop that preserves first-seen casing |
| `parsers/normalizer.py` | 21–27 | Extend `_parse_dates()` to normalize each split token: MM/YYYY → "Mon YYYY", YYYY-MM → "Mon YYYY", full month → 3-letter abbreviation, Present/Current/Now → "Present" |
| `profile_extractor.py` | 1560–1575 | Confirm thin delegate pattern is intact; document the legacy body at 1578–1763 exists only for backward-compat imports |
| `parsers/plain_parser.py` | 708 | Confirm `_dedupe` import from `normalizer` already routes through the fixed version |

## Acceptance Criteria

- [x] `_dedupe(["Python", "python", "SQL", "sql"])` returns exactly 2 items with original first-seen casing preserved ("Python", "SQL")
- [x] `_parse_dates("07/2024 – Present")` returns `("Jul 2024", "Present")`
- [x] `_parse_dates("2024-07 – 2025-01")` returns `("Jul 2024", "Jan 2025")`
- [x] `profile_extractor._parse_plain_resume_text` imports and delegates to `parsers.plain_parser._parse_plain_resume_text` (not the legacy copy)
- [x] All 220 existing tests in the three target files continue to pass with no regressions
- [x] `_parse_dates("Jan 2022 – Present")` still returns `("Jan 2022", "Present")` (already-normalized input passes through unchanged)

## Metrics

| Metric | Before | After |
|---|---|---|
| Tests passing (target suite) | 220 / 220 (baseline) | 220 / 220 (no regression) |
| Skill dedup correctness | Case-sensitive (duplicates possible) | Case-insensitive (canonical casing preserved) |
| Date format consistency | Raw input string (up to 4 variants for same month) | Normalized "Mon YYYY" or "Present" |
| Parser copy count | 2 (canonical + legacy in profile_extractor) | 1 canonical + 1 clearly-marked legacy shim |
| False-positive ATS skill inflation risk | Present (case duplicates counted twice) | Eliminated |
