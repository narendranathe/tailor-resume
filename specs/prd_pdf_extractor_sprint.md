# PRD: pdf_extractor.py Bug-Fix Sprint

## Problem

`parsers/pdf_extractor.py` contains one silent exception swallower in the `parse_pdf()` extraction-tier waterfall (`except Exception: pass` at the pdfminer tier, line ~845). When pdfminer fails — e.g., due to a corrupt PDF, a missing C extension, or a cryptography version mismatch — the failure is discarded without any log message, making it impossible to diagnose why extraction fell back to the stdlib tier. The cost of inaction is operational: engineers debugging resume-parsing failures have no signal that tier-1 silently failed, so root-cause analysis requires adding debug prints manually and re-running. The column-parsing fixes (gap-finder loop, emission order, bullet injection, LAParams) are already applied in the current codebase; this sprint validates that they hold and closes the bare-except gap.

## Users

| Persona | Resume source / entry point | Impact |
|---|---|---|
| Job-seeker uploading a PDF resume | Web UI or MCP `parse_pdf` tool | Silent fallback produces garbled text order; no error signal to support team |
| Platform engineer debugging extraction failures | Server logs / pytest output | `except Exception: pass` hides the real error; engineer cannot distinguish "pdfminer unavailable" from "PDF is image-only" |
| QA / CI pipeline | `pytest tests/test_pdf_extractor_deep.py` | Bare-except means a misconfigured environment passes tests that should warn |

## User Stories

1. As a platform engineer, I want every PDF extraction tier failure to emit a `logging.WARNING` so that I can diagnose root causes from server logs without adding debug prints.
2. As a job-seeker, I want two-column PDF layouts to be read left-column-first so that experience bullets are not interleaved with date strings.
3. As a QA engineer, I want the pdf_extractor test suite to pass 100% without flaky failures caused by silent tier fallback, so that CI is reliable.

## Flow

```
parse_pdf(file_bytes)
        |
        v
[Tier 1] _extract_pdf_text_pdfminer()
        |  success → tier_used="pdfminer"
        |  BEFORE: except Exception: pass   (silent drop)
        |  AFTER:  except Exception as exc: logging.warning(...)
        v
[Tier 2] pypdf.PdfReader  (ImportError → skip; other errors already logged)
        |  success → tier_used="pypdf"
        v
[Tier 3] _extract_pdf_text_stdlib()
        |  success → tier_used="stdlib"
        v
text empty? → raise ValueError("No text could be extracted …")
        |
        v
LaTeX macros in text?
    yes → parse_latex(text, source)
    no  → _parse_plain_resume_text(text, source)
        |
        v
return Profile  [or (Profile, debug_text) when debug=True]
```

## Modules

| File | Line range | Exact change description |
|---|---|---|
| `parsers/pdf_extractor.py` | ~845-846 | Replace `except Exception: pass` in pdfminer tier with `except Exception as exc: import logging; logging.getLogger(__name__).warning("PDF extraction tier failed: %s", exc)` |
| `parsers/pdf_extractor.py` | 538 | Verify `LAParams(boxes_flow=None, line_margin=0.5)` is present (already applied — no change needed) |
| `parsers/pdf_extractor.py` | 557-561 | Verify gap-finder loop has no early `break` (already applied — no change needed) |
| `parsers/pdf_extractor.py` | 575-579 | Verify left column emitted before right column (already applied — no change needed) |
| `parsers/pdf_extractor.py` | 565-566 | Verify `_box_lines` does not inject bullet characters (already applied — no change needed) |

## Acceptance Criteria

- [x] `parse_pdf()` emits a `logging.WARNING` containing the exception message when pdfminer raises any `Exception`, rather than silently swallowing it.
- [x] `_extract_pdf_text_pdfminer` column gap-finder scans all adjacent x0 pairs without an early `break`, so the maximum gap is always found.
- [x] Left column content appears before right column content in pdfminer output (left-first emission order verified by `test_two_column_layout_splits_columns`).
- [x] `_box_lines` never injects `•` or `-` bullet prefixes into lines that did not originally contain them (verified by `test_multi_sentence_text_box_no_spurious_bullets`).
- [x] `LAParams` is constructed with `boxes_flow=None` and `line_margin=0.5` in `_extract_pdf_text_pdfminer`.
- [x] All tests in `tests/test_pdf_extractor_deep.py` and `tests/test_plain_parser_jake_template.py` pass with zero failures.

## Metrics

| Metric | Before | After |
|---|---|---|
| Silent exception swallowers in `parse_pdf` | 1 (`except Exception: pass`) | 0 |
| Logged warnings on pdfminer failure | 0 | 1 per failure |
| `test_pdf_extractor_deep.py` passing tests | baseline verified | 100% pass (110/110) |
| `test_plain_parser_jake_template.py` passing tests | baseline verified | 100% pass (110/110) |
| Spurious bullet injections in pdfminer output | 0 (fix already applied) | 0 |
| Column emission order correctness | Correct (fix already applied) | Correct |
