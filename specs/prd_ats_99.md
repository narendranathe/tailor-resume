# PRD: 99+ ATS Score — Closing the Gap Between Spec and Implementation

> Product-Driven Development pipeline: **Problem → Users → Stories → Flow → Modules → Acceptance → Metrics**.
> All architectural decisions made here will be appended to `specs/README.md` upon implementation.

---

## Overview

A parallel audit of `jd_gap_analyzer.py`, `star_validator.py`, `latex_renderer.py`, `text_utils.py`, and `pipeline.py` found 15 concrete bugs and gaps that prevent any resume from scoring 99+ ATS — even a perfectly-written one. The most critical are: an `int()` truncation that hard-caps at 99, a 3-char token filter that drops "sql", "etl", "ml", "ai", "dag" from every keyword comparison, and a commented-out summary block that silently omits the summary section from every rendered PDF. This PRD specifies all 15 fixes with exact file locations.

## Problem Statement

Four concrete blockers prevent 99+ ATS scores today:

1. **`int()` truncation instead of `round()`** — a formula result of 0.999 becomes 99, not 100. The highest achievable score is 99 regardless of how good the resume is.
2. **3-char token filter drops the most important keywords** — "sql", "etl", "dag", "ml", "ai", "bi", "aws", "gcp" are all silently excluded from keyword overlap. A JD with 10 occurrences of "SQL" scores 0 keyword overlap on "SQL" because the token is 3 chars.
3. **Summary section is commented out in the LaTeX template** — `% \section{Summary}` means no generated resume ever includes a summary, eliminating the primary keyword-dense section that ATS parsers weight most heavily.
4. **Bullet quality defaults to 0.0 for all plain-text inputs** — when resume input is not valid JSON, `_extract_bullets_for_scoring()` returns `[]` and the 20% quality component is zero, capping ATS at 80 before the first bullet is written.

Secondary blockers (each costs 2–8 points):

5. **ACTION_VERBS missing 25+ common strong verbs** — "spearheaded", "mentored", "resolved", "partnered", "instrumented", "benchmarked" all score 0 on STAR Action. Senior-level bullets frequently start with these words.
6. **TOOL_VOCAB missing 40+ current tools** — Snowflake, BigQuery, Prefect, DuckDB, Polars, Datadog, Fivetran, Airbyte, Ray, Bedrock, VertexAI, Feast, gRPC, etc. Bullets mentioning these tools get `extract_tools()` returning `[]` and score low confidence.
7. **Seniority word list has 5 words** — "VP", "head of", "tech lead", "founding engineer", "distinguished" all miss, causing a 7-point seniority penalty on any resume with these titles.
8. **Recommendations cover only 2 of 10 signal categories** — the other 8 categories produce only a generic fallback message even at 0% coverage.
9. **Substring category matching inflates/deflates scores** — "lead" matches "already" and "upload"; "test" matches "protest". Word-boundary matching fixes false positives.
10. **`min_freq=2` drops single-occurrence critical terms** — "soda", "trino", "polars" appear once in a JD but are critical differentiators. They never appear in the gap report.
11. **ACTION_VERBS window: first 6 words only for long bullets** — bullets starting with a tech name ("Terraform modules for EKS...") fail STAR Action even when a strong verb appears at position 8.
12. **RESULT_SIGNAL_WORDS too permissive** — "improved developer experience" passes `_has_result()` via signal words, giving full STAR credit to vague bullets.
13. **Word-count violation does not reduce quality score** — a 30-word bullet scores 1.0 quality even though it would be truncated mid-sentence at render time.
14. **extract_metrics() misses** — `sub-100ms`, `<100ms`, `"nearly doubled"`, headcount (`"a team of 8"`), NPS (`NPS +32`), ranked ordinals (`"top 5%"`).
15. **GitHub URL placeholder absent from LaTeX template** — `{{GITHUB_URL}}` is in the renderer's header dict but not in `resume_template.tex`, silently omitting GitHub from the rendered PDF.

## Target Users

| Persona | Description | Impact |
|---|---|---|
| **Narendra applying to Data Engineering roles** | Uploads a Jake-template PDF, pastes a JD, expects a tailored resume that passes an ATS screen. | Direct — every bug listed above affects every run. |
| **Future SaaS users (v3)** | Paying subscribers who expect "99+ ATS" as the product promise. | Brand-critical — delivering < 99 on a clean JD/profile match is a product failure. |

## User Stories

1. **As a user with a perfectly matched profile**, when I upload my resume and paste a matching JD, the ATS score should be 99 or 100 — not capped at 99 by arithmetic truncation.
2. **As a user**, my summary paragraph should appear in the rendered PDF and contain JD keywords, so ATS parsers see the most keyword-dense section of my resume.
3. **As a user using a plain-text blob** (not JSON), the ATS score should reflect my actual bullet quality — not default to 0% for the 20% quality component.
4. **As a user whose resume mentions "SQL", "ETL", "ML"**, these should count toward keyword overlap — they should not be silently dropped by a 3-char filter.
5. **As a user with a Staff/Principal title**, my resume should get full seniority credit without requiring "Senior" in the title.
6. **As a user receiving gap recommendations**, every missing signal category should generate a specific, actionable recommendation — not a generic fallback for 8 of 10 categories.
7. **As a user with bullets starting with "spearheaded", "mentored", "partnered"**, these should count as action verbs — not score 0 on STAR and be flagged as weak bullets.

## Detailed Flow

### Current scoring path (broken at 7 points)

```
JD text + Resume text
  → tokenize() → min_len > 3 filter (DROPS "sql", "ml", "etl") → overlap ratio
  → int(score * 100)  ← TRUNCATION BUG
  → bullet_quality:
      plain-text input → _extract_bullets_for_scoring() → [] → 0.0 (DEAD)
  → seniority: 5-word list misses "tech lead", "VP"
  → summary: commented-out in template → never rendered
  → recommendations: only 2 of 10 categories covered
```

### Fixed scoring path

```
JD text + Resume text
  → tokenize() → min_len >= 2 filter → "sql", "ml", "etl" included
  → round(score * 100)  ← correct rounding
  → bullet_quality:
      plain-text → regex extract bullets → scored inline (no longer dead)
  → seniority: 12-word list covers "tech lead", "VP", "head of"
  → summary: uncommented in template → rendered, keyword-dense
  → recommendations: all 10 categories have specific messages
```

## Module Breakdown

### Module 1 — `jd_gap_analyzer.py`: arithmetic fix (Fix 1)

**File:** `scripts/jd_gap_analyzer.py`
**Line:** `estimate_ats_score()` — the final `return int(...)` line.
**Fix:** `return int(round(score * 100, 0))`
**Impact:** Up to +1 point; removes the artificial 99 ceiling.

### Module 2 — `jd_gap_analyzer.py` + `text_utils.py`: 3-char token filter (Fix 2)

**File:** `jd_gap_analyzer.py` `keyword_gaps()`, `text_utils.py` `tokenize()`
**Fix:** Change `len(term) > 3` to `len(term) >= 2` everywhere the filter appears. Add explicit keep-list for known 2-char domain terms: `{"ml", "ai", "bi", "qa", "go"}`.
**Impact:** "sql" (3 chars), "etl" (3), "dag" (3), "ml" (2), "ai" (2), "bi" (2) all re-enter keyword overlap. On a DE JD with 15 occurrences of "SQL", this alone can add 8–12 points to keyword overlap.

### Module 3 — `resume_template.tex`: uncomment summary section (Fix 3)

**File:** `templates/resume_template.tex`
**Fix:** Remove the `%` comment characters from the summary block so it renders when `{{SUMMARY}}` is non-empty. Add a guard: only emit the section if `{{SUMMARY}}` is non-empty (via LaTeX conditional or by having the renderer skip the block when summary is blank).
**Impact:** The summary is the highest keyword-density section on a resume. Its absence means ~15–20% of the JD keyword signal is invisible to ATS parsers.

### Module 4 — `jd_gap_analyzer.py`: bullet quality fallback for plain-text (Fix 4)

**File:** `scripts/jd_gap_analyzer.py` `_extract_bullets_for_scoring()`
**Fix:** When `resume_text` is not valid JSON, regex-extract bullet lines from plain text using `^[\•\-\*]\s+(.+)` and `^\d+\.\s+(.+)`. Score those extracted bullets via `bullet_quality_score()`. Fall back to `0.5` default (not `0.0`) when no bullets are extractable.
**Impact:** Removes the 20-point cap on plain-text resumes. Estimated +15 points for typical resume blobs.

### Module 5 — `star_validator.py`: ACTION_VERBS expansion (Fix 5)

**File:** `scripts/star_validator.py`
**Fix:** Add 25 verbs to `ACTION_VERBS`:
`spearheaded, authored, mentored, resolved, diagnosed, hardened, instrumented, benchmarked, abstracted, parallelized, tuned, provisioned, onboarded, coordinated, forecasted, exposed, published, validated, documented, influenced, aligned, partnered, evangelized, operationalized, introduced, presented, defined, enforced, adopted, decommissioned`
**Impact:** Senior-IC and staff-level bullets start with these words. Eliminating false 0-STAR scores raises the 20% quality component by an estimated 5–10 points on typical senior resumes.

### Module 6 — `star_validator.py`: action verb search window (Fix 6)

**File:** `scripts/star_validator.py` `_has_action()`
**Fix:** For bullets with length > 12 words, search the full bullet for ANY action verb (not just the first 6 words). The current logic only falls back to all-words search for bullets ≤ 12 words.
**Fix:** Change the condition from `if len(words) <= 12` to always search all words for action verbs, but give a bonus flag `verb_at_start` when the verb is in the first 6 words (for future scoring refinement).
**Impact:** Bullets like "Terraform modules for EKS deployments reduced provisioning time from 3 days to 4 hours" (16 words, "reduced" at position 8) currently score 0 on Action. After fix: STAR 2/2.

### Module 7 — `text_utils.py`: TOOL_VOCAB expansion (Fix 7)

**File:** `scripts/text_utils.py`
**Fix:** Add 45 tools to `TOOL_VOCAB`:
Cloud services: `Snowflake, BigQuery, Redshift, Athena, Glue, Synapse, ADLS, S3, Lambda, ECS, EKS, AKS, Cloud Run`
Orchestration: `Prefect, Mage, Dagster`
Data: `DuckDB, Polars, Trino, Flink, Pulsar, Fivetran, Airbyte, Arrow, Parquet, Avro`
Observability: `Datadog, OpenTelemetry, Splunk, Sentry`
ML/AI: `Ray, Bedrock, VertexAI, Weights & Biases, Feast, Tecton, SageMaker, LlamaIndex, Weaviate, Qdrant, ChromaDB`
DevOps: `ArgoCD, Helm, Pulumi, Crossplane`
Protocols: `gRPC, Protobuf`
Languages: `Go, Rust, TypeScript, Scala`
**Impact:** Bullets mentioning these tools currently score `confidence: low` (0 tools found). After fix: `confidence: high/medium` when 1–2+ tools are present.

### Module 8 — `jd_gap_analyzer.py`: seniority word list (Fix 8)

**File:** `scripts/jd_gap_analyzer.py` `_SENIORITY_WORDS` (or equivalent constant)
**Fix:** Expand to 12 terms:
`senior, lead, principal, staff, architect, manager, director, vp, "head of", "tech lead", "founding engineer", distinguished, fellow`
**Impact:** Removes 7-point seniority penalty for users with "Tech Lead", "VP of Engineering", "Head of Data" or similar titles.

### Module 9 — `jd_gap_analyzer.py`: recommendations for all 10 categories (Fix 9)

**File:** `scripts/jd_gap_analyzer.py` `build_gap_signals()` recommendations block
**Fix:** Replace the 2-category hardcoded `if` chain with a dict mapping all 10 `SIGNAL_TAXONOMY` keys to specific recommendation messages. Add a threshold: any category with < 60% coverage and ≥ 1 JD hit generates a category-specific recommendation.
**Impact:** Users with gaps in orchestration, streaming, ML platform, architecture, cloud infra, SQL modeling, or leadership now get actionable guidance instead of a generic fallback.

### Module 10 — `jd_gap_analyzer.py`: word-boundary category matching (Fix 10)

**File:** `scripts/jd_gap_analyzer.py` `analyze_category_coverage()`
**Fix:** Change substring `keyword in text` to regex word-boundary match: `re.search(r'\b' + re.escape(keyword) + r'\b', text, re.IGNORECASE)`. For multi-word terms ("data quality", "unit test"), the existing substring match is correct and should be preserved.
**Impact:** "lead" no longer matches "already". "test" no longer matches "protest". Coverage scores become more accurate — false inflations go down, exposing real gaps.

### Module 11 — `jd_gap_analyzer.py`: min_freq for short critical terms (Fix 11)

**File:** `scripts/jd_gap_analyzer.py` `keyword_gaps()`
**Fix:** Apply `min_freq=1` (not 2) for any term in a short-term keep-list: `{"soda", "trino", "polars", "flink", "ray", "dbt", "iceberg", "avro", "grpc", "feast"}`. Keep `min_freq=2` for all other terms to suppress noise.
**Impact:** Single-occurrence critical tool names now appear in the gap report and drive recommendations.

### Module 12 — `text_utils.py`: extract_metrics() patterns (Fix 12)

**File:** `scripts/text_utils.py`
**Fix:** Add 5 new metric patterns to `_METRIC_PATTERNS`:
- Sub-millisecond: `r'sub[-\s]?\d+ms|<\d+\s*ms'` → "sub-100ms", "<50ms"
- Headcount: `r'(?:a\s+)?team\s+of\s+\d+|\d+[-\s]engineer|\d+[-\s]person'` → "team of 8", "12-engineer"
- Ranked ordinal: `r'(?:top|#)\s*\d+\s*%?'` → "top 5%", "#1 team"
- Nearly doubled/tripled: `r'(?:nearly|almost)\s+(?:doubled|tripled|halved)'`
- NPS/satisfaction: `r'NPS\s*[+-]?\d+|\d+(?:\.\d+)?/\d+\s*(?:satisfaction|score|rating)'`
**Impact:** Bullets that describe sub-millisecond latency, team size, or satisfaction scores now generate metrics and score `confidence: high`.

### Module 13 — `resume_template.tex`: GitHub URL placeholder (Fix 13)

**File:** `templates/resume_template.tex`
**Fix:** Add `\href{{{GITHUB_URL}}}{\underline{{{GITHUB_DISPLAY}}}}` to the contact line, guarded by a check in the renderer for non-empty `github` field.
**Impact:** GitHub profile is a primary signal for technical candidates. Its current omission from the rendered PDF is a bug.

### Module 14 — `star_validator.py`: word-count penalty in quality score (Fix 14)

**File:** `scripts/star_validator.py` `bullet_quality_score()`
**Fix:** If `word_count > MAX_BULLET_WORDS`, apply a 0.1 quality penalty (score caps at 0.9 instead of 1.0). This incentivizes the iterative loop to shorten bullets before the renderer truncates them mid-sentence.
**Impact:** Avoids the scenario where a 30-word bullet scores quality 1.0 but is then truncated to a grammatically broken 20-word fragment at render time.

## Acceptance Criteria

### Must-pass (blocking)

- [ ] `round()` not `int()` in `estimate_ats_score()` — a raw value of 0.999 returns 100.
- [ ] "sql", "etl", "dag" appear in keyword overlap when present in both JD and resume.
- [ ] A resume rendered from a profile with non-empty `summary` field includes a `Summary` section in the PDF.
- [ ] A plain-text resume blob passed to `run_analysis()` produces a non-zero bullet quality score.
- [ ] `python -m pytest tests/ -v --ignore=tests/test_billing.py --ignore=tests/test_web_api.py --ignore=tests/test_api_server.py --ignore=tests/test_mcp_server.py --ignore=tests/test_profile_patch.py --ignore=tests/test_setup_routes.py` passes with 0 failures.

### Should-pass (non-blocking)

- [ ] "spearheaded", "mentored", "partnered" appear in ACTION_VERBS and cause `_has_action() == True`.
- [ ] "Snowflake", "BigQuery", "Prefect", "DuckDB" appear in TOOL_VOCAB and cause `extract_tools()` to return them.
- [ ] "tech lead" and "VP" in a resume produce `seniority_score = 1.0`.
- [ ] A JD with 0% `orchestration` category coverage produces a specific Airflow/Dagster recommendation.
- [ ] "sub-100ms" in a bullet causes `extract_metrics()` to return a match.
- [ ] A 25-word bullet scores `quality < 1.0` due to the word-count penalty.

## Non-Functional Requirements

- **No new dependencies.** All fixes are stdlib regex and constant additions.
- **No scoring regressions.** The ATS formula weights (40/30/20/10) are unchanged.
- **Backward-compatible.** Existing profile JSON format unchanged. Resume template adds summary but existing renders still valid.

## Build Order

Fix 1 (round) → Fix 2 (token filter) → Fix 3 (summary template) → Fix 4 (plain-text bullet extraction) → Fix 5 (ACTION_VERBS) → Fix 6 (verb window) → Fix 7 (TOOL_VOCAB) → Fix 8 (seniority) → Fix 9 (recommendations) → Fix 10 (word boundary) → Fix 11 (min_freq) → Fix 12 (metrics patterns) → Fix 13 (GitHub URL) → Fix 14 (word-count penalty)

## Success Metrics

| Metric | Before | Target |
|---|---|---|
| Max achievable ATS score | 99 (int truncation) | 100 |
| Keyword overlap: "sql", "etl", "dag" in both JD+resume | 0 (filtered out) | Counted |
| Summary appears in rendered PDF | Never | Always when non-empty |
| Bullet quality for plain-text input | 0.0 (dead) | ~0.5–0.8 |
| ACTION_VERBS coverage for senior-IC bullets | ~60% | ~90% |
| TOOL_VOCAB coverage for 2026 stack | ~38 tools | ~83 tools |
| Recommendations covering all 10 categories | 2/10 | 10/10 |
| Test suite failures | 0 | 0 |

## Definition of Done

- [ ] All 14 fixes implemented.
- [ ] Test suite: 0 failures, new tests added for each fix in `tests/test_jd_gap_analyzer.py` and `tests/test_star_validator.py`.
- [ ] `python scripts/sync_global.py` propagates changes.
- [ ] `specs/README.md` updated.
- [ ] Rendered sample resume includes Summary section.
