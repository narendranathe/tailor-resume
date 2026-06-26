# PRD: Scoring Pipeline Sprint — ATS Accuracy & Vocabulary Fixes

## Problem

The ATS scoring pipeline in `jd_gap_analyzer.py`, `text_utils.py`, and `star_validator.py` contains five compound defects that suppress scores unfairly and hide actionable information from candidates. Specifically: the plain-text bullet fallback assigns `confidence='low'` which contributes zero to bullet quality scoring, meaning resumes without JSON profiles are systematically scored lower; the tokenizer previously used `> 3` length filter (now `>= 2`) but the STOPWORDS set and `_CATEGORY_RECS` keys still use `.title()` form which never matches the lowercase-underscore SIGNAL_TAXONOMY keys (causing all category-specific recommendations to silently drop); `_SENIORITY_WORDS` and `ACTION_VERBS`/`TOOL_VOCAB` are missing modern senior-IC terms; and bare `except` blocks swallow errors silently making debugging impossible. Together these defects cause ATS scores to top out artificially low, suppress ML/AI/SQL/CI/ETL tokens from gap analysis, show generic instead of category-specific recommendations, and hide scoring errors from operators. The cost of inaction is candidates receiving misleading ATS estimates and missing targeted resume advice, degrading product trust.

## Users

| Persona | Resume source / entry point | Impact |
|---|---|---|
| Job-seeker (plain-text resume) | Pastes raw resume text into CLI or MCP tool | Receives suppressed ATS score due to `confidence='low'` on all bullets |
| Job-seeker (JSON profile) | Uploads structured profile via web or MCP | Loses category-specific recommendations because `_CATEGORY_RECS` keys never match SIGNAL_TAXONOMY |
| Senior IC / Staff engineer | Submits resume with ML/AI/ETL/CI experience | Short acronyms filtered out of gap analysis, missing seniority vocab lowers score |
| Resume coach / operator | Monitors scoring pipeline logs | Bare `except` silently swallows errors, making root-cause diagnosis impossible |

## User Stories

1. As a job-seeker submitting a plain-text resume, I want bullet quality to contribute fairly to my ATS score so that I receive an accurate estimate even without a structured JSON profile.
2. As a senior data engineer with ML/AI/ETL experience, I want those acronyms to appear in keyword gap analysis so that I understand exactly which JD terms I am missing.
3. As a resume coach reviewing the gap report, I want to see the ATS score broken down by component (keyword, category, bullet quality, seniority) so that I can give targeted advice on which area to improve first.

## Flow

```
BEFORE:
  plain-text resume
       |
  _extract_bullets_for_scoring()
       |
  confidence='low'  ──────────────────► bullet_quality_avg suppressed
       |
  estimate_ats_score()  ──────────────► score ceiling ~60-65
       |
  run_analysis()
       |
  _CATEGORY_RECS.get(s.category)  ────► None (keys never match — .title() vs snake_case)
       |
  recommendations []  ────────────────► only generic "Critical" or fallback line shown


AFTER:
  plain-text resume
       |
  _extract_bullets_for_scoring()
       |
  confidence='medium'  ───────────────► bullet_quality_avg reflects real quality
       |
  estimate_ats_score()  ──────────────► score ceiling 90+ for strong resumes
       |
  breakdown line appended to gap_lines ► "ATS Score Breakdown: KW 72% x40% + ..."
       |
  run_analysis()
       |
  _CATEGORY_RECS.get(s.category)  ────► matched via snake_case key
       |
  recommendations []  ────────────────► specific, actionable per-category rec shown
```

## Modules

| File | Line range | Exact change description |
|---|---|---|
| `jd_gap_analyzer.py` | 244–250 | `_extract_bullets_for_scoring`: change `confidence='low'` to `confidence='medium'` for plain-text regex-extracted bullets |
| `jd_gap_analyzer.py` | 244–250 | `_extract_bullets_for_scoring`: replace bare `except Exception:` with `except Exception as exc:` + `logging.warning(...)` |
| `jd_gap_analyzer.py` | 193–230 | `estimate_ats_score`: append ATS breakdown line to a module-level `_last_ats_breakdown` store; expose via `run_analysis` appending to `recommendations` |
| `jd_gap_analyzer.py` | 254–265 | `_CATEGORY_RECS`: change all keys from `.title()` form (e.g. `"Testing Ci Cd"`) to exact SIGNAL_TAXONOMY snake_case (e.g. `"testing_ci_cd"`) |
| `jd_gap_analyzer.py` | 187–190 | `_SENIORITY_WORDS`: add `'tech lead'`, `'head of'`, `'distinguished'`, `'fellow'` |
| `text_utils.py` | 190–207 | `STOPWORDS`: confirm `sql`,`ml`,`ai`,`ci`,`etl` absent; `tokenize`: confirm `len(t) >= 2` |
| `star_validator.py` | 28–47 | `ACTION_VERBS`: add any missing verbs from the required senior-IC list |
| `star_validator.py` | — | `TOOL_VOCAB` is defined in `resume_types.py`; add missing tools there (not in scope — resume_types.py not owned); verify via star_validator import |

## Acceptance Criteria

- [x] `tokenize("ml ai sql etl ci")` returns all 5 tokens (none filtered by length or stopwords)
- [x] `_extract_bullets_for_scoring` on plain-text input returns bullets with `confidence='medium'`, not `'low'`
- [x] `_CATEGORY_RECS` has entries for all 10 SIGNAL_TAXONOMY keys in snake_case; `run_analysis` surfaces category-specific recommendations
- [x] `estimate_ats_score` appends a breakdown line containing "ATS Score Breakdown:" to the gap report recommendations
- [x] `except Exception:` bare block in `_extract_bullets_for_scoring` replaced with `except Exception as exc:` + `logging.getLogger(__name__).warning(...)`
- [x] `ACTION_VERBS` contains all required senior-IC verbs: `architected`, `owned`, `drove`, `scaled`, `shipped`, `launched`, `migrated`, `automated`, `standardized`, `eliminated`, `reduced`, `increased`, `improved`, `built`, `created`, `designed`, `developed`, `implemented`, `led`, `managed`, `mentored`, `optimized`, `refactored`, `streamlined`, `transformed`
- [x] `_SENIORITY_WORDS` contains `tech lead`, `head of`, `distinguished`, `fellow`
- [x] All existing pytest tests in `test_jd_gap_analyzer.py` and `test_star_validator.py` pass

## Metrics

| Metric | Before | After |
|---|---|---|
| ATS score ceiling (plain-text strong resume) | ~62 (bullet quality = 0 for all low-confidence) | ~78+ (medium confidence contributes 0.05/bullet) |
| Category-specific recommendations surfaced | 0 (all `_CATEGORY_RECS.get()` return None) | Up to 5 (one per top missing signal) |
| ATS breakdown visibility | Not shown | Shown as "ATS Score Breakdown: KW X% × 40% + ..." line |
| Short-acronym tokens in gap analysis (ml/ai/sql/etl/ci) | 0 if `> 3` filter was active | All 5 pass through with `>= 2` filter |
| Bare except blocks silencing errors | 1 | 0 |
| Test pass rate | Baseline (run before sprint) | 100% green |
