# Ubiquitous Language — tailor-resume

> **Principle**: When multiple words exist for the same concept, one canonical term is chosen.
> All aliases are listed so they can be actively avoided.
> Consistent usage across code, tests, docs, and conversation is the goal.

---

## 1. Resume Data Model

| Canonical Term | Definition | Aliases to Avoid |
|---|---|---|
| **Profile** | The canonical, normalised representation of all resume data extracted from one or more artifacts. Contains `experience`, `projects`, `skills`, `education`, `certifications`. | *resume object*, *candidate data*, *parsed resume* |
| **Role** | A single employment entry inside `Profile.experience`. Has `title`, `company`, `start`, `end`, `location`, and a list of Bullets. | *job*, *position*, *work entry*, *experience item* |
| **Bullet** | One achievement or responsibility line item inside a Role or Project. Has `text`, `metrics`, `tools`, `evidence_source`, `confidence`. | *achievement*, *responsibility*, *line item*, *bullet point* |
| **Project** | A side project, personal project, or open-source contribution inside `Profile.projects`. Has `name`, `stack`, `date`, and a list of Bullets. | *side project*, *portfolio item*, *personal project* |
| **Skills** | A flat list or categorised dict of technology keywords on the Profile. | *technical skills*, *tech stack*, *technologies* |
| **Education** | List of degree entries on the Profile (school, degree, graduation date). | *academic history*, *degree*, *schooling* |
| **Certifications** | List of licenses, credentials, or recognitions on the Profile. | *certs*, *licenses*, *credentials* |
| **evidence\_source** | Tag on every Bullet recording which parser or process produced it. Values: `blob`, `latex_resume`, `markdown_resume`, `linkedin_pdf`, `pdf_upload`, `docx_upload`, `ai_enrichment`, `unknown`. | *source*, *origin*, *provenance* |
| **confidence** | Quality signal on a Bullet: `high` (metric-dense), `medium`, or `low` (vague). | *quality score*, *bullet score*, *strength* |

### Relationships

- A **Profile** contains zero or more **Roles** (via `experience`).
- A **Role** contains zero or more **Bullets**.
- A **Profile** contains zero or more **Projects**.
- A **Project** contains zero or more **Bullets**.
- A **Bullet** belongs to exactly one **Role** or **Project**.

---

## 2. Artifact & Parsing

| Canonical Term | Definition | Aliases to Avoid |
|---|---|---|
| **Artifact** | A single input file or text blob fed to the pipeline. Identified by `PATH:FORMAT`. | *input*, *source file*, *resume file* |
| **Format** | The declared type of an Artifact: `blob`, `markdown`, `latex`, `linkedin`, `pdf`, `docx`. | *file type*, *input type*, *mode* |
| **Blob** | Free-form work-history text pasted directly (no markup). Parsed by `parse_blob()`. | *paste*, *raw text*, *plain text* |
| **Extraction Tier** | One of three ordered PDF text extraction strategies. Tier 1 wins; others are fallbacks. | *fallback*, *strategy*, *method* |
| **Tier 1 (pdfminer)** | `pdfminer.six` — reads ToUnicode CMap; best for LaTeX/CMR fonts and multi-column layouts. | *pdfminer extractor*, *primary extractor* |
| **Tier 2 (pypdf)** | `pypdf` — fast; best for Word-generated PDFs. Does not read ToUnicode CMap. | *pypdf extractor*, *secondary extractor* |
| **Tier 3 (stdlib)** | Pure-Python PDF parser; no external dependencies; used only when Tiers 1 and 2 are unavailable. | *stdlib extractor*, *fallback extractor*, *last resort* |
| **OT1 Artifact** | A garbled character produced when a Tier 2/3 extractor decodes a LaTeX CMR-font glyph without a ToUnicode CMap. The CMR bullet (0x0F) decodes as `"ffi"`; icon-font glyphs decode as `"j"`. | *encoding artifact*, *glyph corruption*, *ffi prefix* |
| **OT1 Normalization** | The post-processing pass (`_normalize_ot1_artifacts()`) that converts OT1 Artifact prefixes to real bullet characters (•) and drops lone icon lines. Applied to all tiers in `parse_pdf()`. | *glyph fix*, *encoding fix*, *OT1 cleanup* |
| **merge\_profiles()** | Combine two or more parsed Profiles into one canonical Profile, de-duplicating Roles by company+date. | *merge*, *combine*, *union profiles* |
| **auto\_detect\_format()** | Heuristic function that infers the Format of an Artifact from its content without the user declaring it. | *format detection*, *auto-detect* |

---

## 3. Gap Analysis

| Canonical Term | Definition | Aliases to Avoid |
|---|---|---|
| **Job Description (JD)** | The target job posting text. Input to the gap analysis pipeline. | *job post*, *JD text*, *posting* |
| **Signal Category** | One of 10 named capability buckets (e.g., `testing_ci_cd`, `streaming_realtime`) used to cluster JD keywords. | *category*, *bucket*, *domain area* |
| **GapSignal** | A single Signal Category where the JD demonstrates need but the Profile has insufficient coverage. Has `category`, `keywords`, `jd_frequency`, `resume_coverage`, `priority`, `suggested_angles`. | *gap*, *missing skill*, *weakness* |
| **GapReport** | The complete gap analysis output: `top_missing` GapSignals, `keyword_gaps`, `ats_score_estimate`, `recommendations`. | *analysis result*, *gap output* |
| **jd\_frequency** | Count of how many times a Signal Category's keywords appear in the JD. Measures JD emphasis. | *frequency*, *JD weight*, *keyword count* |
| **resume\_coverage** | Float 0.0–1.0 measuring what fraction of a Signal Category's keywords appear in the Profile. | *coverage score*, *match rate*, *keyword coverage* |
| **ATS Score Estimate** | A 0–100 rough relevance score computed from keyword overlap and Signal Category coverage. Not a real ATS system's score. | *match score*, *relevance score*, *ATS score* |
| **ATS Relevance Gate** | The intake decision threshold: ≥80 proceed (same role), 60–79 proceed with caveats, <50 decline. Applied before any rewriting. | *relevance gate*, *score gate*, *intake gate* |
| **Honest Ceiling** | The maximum ATS Score achievable given the candidate's actual experience, even after ideal rewriting. Reported explicitly when tech gaps exist. | *ceiling*, *max score*, *upper bound* |
| **Keyword Gap** | A high-frequency JD keyword that is absent from the Profile entirely (not covered by any Signal Category keyword list). | *missing keyword*, *absent term* |
| **Suggested Angle** | A closing question or prompt per GapSignal designed to surface hidden evidence the candidate hasn't yet articulated. | *elicitation prompt*, *follow-up question*, *angle* |
| **Priority** | GapSignal urgency: `high` (core requirement), `medium` (nice-to-have), `low` (bonus). | *importance*, *weight*, *urgency* |

### Signal Categories (canonical names)

`testing_ci_cd` · `data_quality_observability` · `orchestration` · `semantic_layer_governance` · `architecture_finops` · `streaming_realtime` · `ml_ai_platform` · `cloud_infra` · `leadership_ownership` · `sql_data_modeling`

---

## 4. LaTeX Rendering

| Canonical Term | Definition | Aliases to Avoid |
|---|---|---|
| **Template** | A `.tex` file with `{{PLACEHOLDER}}` tokens that `render_template()` fills in. | *LaTeX template*, *base template*, *skeleton* |
| **Placeholder** | A `{{UPPER_SNAKE_CASE}}` token in the Template replaced at render time (e.g., `{{NAME}}`, `{{EXPERIENCE}}`). | *variable*, *token*, *slot* |
| **render\_template()** | The function that substitutes all Placeholders in a Template with rendered section strings. | *fill template*, *compile template* |
| **build\_from\_profile()** | Orchestrates the full LaTeX resume build: renders all sections, fills the Template, returns `.tex` string. | *build resume*, *render resume*, *generate LaTeX* |
| **\\resumeSubheading** | LaTeX macro for a Role header: `{title}{dates}{company}{location}`. | *role header macro*, *subheading* |
| **\\resumeItem** | LaTeX macro wrapping a single Bullet text. | *item macro*, *bullet macro* |
| **\\resumeProjectHeading** | LaTeX macro for a Project header. | *project header macro* |
| **LaTeX Escape** | Converting special characters (`&`, `%`, `$`, `#`, `_`, `{`, `}`, `~`, `^`, `\\`) to their LaTeX-safe equivalents via `escape()`. | *escaping*, *sanitise* |
| **Bullet Formula** | The preferred structure for a Bullet: *"Accomplished X as measured by Y by doing Z."* Enforces quantification. | *STAR format*, *XYZ format*, *achievement template* |

---

## 5. Pipeline & CLI (updated)

| Canonical Term | Definition | Aliases to Avoid |
|---|---|---|
| **Pipeline** | The end-to-end flow: parse Artifacts → merge Profile → run gap analysis → render LaTeX. Orchestrated by `pipeline.py`. | *workflow*, *process*, *run* |
| **TailorConfig** | Dataclass holding all pipeline inputs: artifact paths, JD path, header fields, template path. Passed to `execute()` or `execute_text()`. | *config*, *pipeline config*, *settings* |
| **TailorResult** | Dataclass holding pipeline outputs: `.tex` string, GapReport, ATS Score Estimate. Returned by `execute()` and `execute_text()`. | *result*, *output*, *pipeline output* |
| **execute()** | File-based pipeline entry point in `pipeline.py`. Takes a TailorConfig with file paths; used by CLI. | *run pipeline*, *file pipeline* |
| **execute\_text()** | Text-based pipeline entry point in `pipeline.py`. Takes raw text strings instead of file paths; used by MCP tools and the web API. | *text pipeline*, *API pipeline* |
| **CLI** | `cli.py` — the command-line entry point (`tailor-resume` command). Accepts `--artifact`, `--jd`, `--output`, header flags. Delegates to `execute()`. | *command line*, *CLI tool*, *script* |
| **`--artifact PATH:FORMAT`** | Repeatable CLI flag specifying one Artifact. The `:FORMAT` suffix declares its Format. | *input flag*, *artifact flag* |
| **Header Injection** | Passing `--name`, `--email`, `--phone`, `--linkedin`, `--github`, `--portfolio` at CLI runtime to fill contact Placeholders without embedding PII in files. | *PII injection*, *contact injection*, *header fields* |

---

## 5b. Parser & Store Packages (new)

| Canonical Term | Definition | Aliases to Avoid |
|---|---|---|
| **parsers/** | The package of format-specific extractor modules split from the monolithic `profile_extractor.py`. Contains `latex_parser`, `pdf_extractor`, `plain_parser`, `markdown_parser`, `docx_extractor`, `normalizer`. | *parsers package*, *extractors*, *parser modules* |
| **plain\_parser** | Module handling plain-text and blob extraction (`_parse_plain_resume_text()`). | *text parser*, *blob parser* |
| **normalizer** | Module containing `_normalize_ot1_artifacts()` and shared text normalization utilities. | *normalizer module*, *OT1 module* |
| **profile\_extractor.py (shim)** | Compatibility re-export shim at the scripts root that re-exports everything from `parsers/`. Exists so existing imports don't break. Not the implementation. | *profile extractor*, *main parser* |
| **stores/** | The package of RAG profile storage implementations: `PineconeStore`, `SQLiteStore`, and the `get_store()` factory. | *stores package*, *storage package* |
| **EmbedFn** | Type alias `Callable[[str], List[float]]` injected into stores at construction. Prevents dimension mismatch (OpenAI 1536-dim vs TF-IDF 128-dim) corrupting cosine scores. | *embedder*, *embedding function*, *embed callable* |
| **PineconeStore** | Vector store backed by Pinecone. Active when `PINECONE_API_KEY` is set. | *Pinecone store*, *cloud vector store* |
| **SQLiteStore** | Local vector store backed by SQLite. Used when `PINECONE_API_KEY` is absent. | *SQLite store*, *local store* |
| **get\_store()** | Factory that returns `PineconeStore` if `PINECONE_API_KEY` is set, else `SQLiteStore`. | *store factory*, *get store* |
| **rag\_store.py (shim)** | Compatibility re-export shim at the scripts root that re-exports from `stores/`. Not the implementation. | *rag store*, *store module* |
| **Storage Fallback Pattern** | Convention used across storage (`db/supabase.py`) and usage metering (`middleware/usage.py`): Supabase when env vars are set, SQLite at `~/.tailor_resume/` otherwise. New stores must follow this pattern. | *fallback pattern*, *store fallback* |

---

## 5c. Web Backend & MCP (new)

| Canonical Term | Definition | Aliases to Avoid |
|---|---|---|
| **Web Backend** | FastAPI app in `web_app/backend/`. Uses the `create_app()` factory. Clerk RS256 JWT auth. Deployed to `tailor-resume-api.fly.dev`. | *backend*, *API server*, *web API* |
| **create\_app()** | FastAPI application factory in `web_app/backend/app/main.py`. Mounts `/api/v1` routes + CORS. Mirrors the autoapply-ai pattern. | *app factory*, *FastAPI factory* |
| **MCP Server** | `mcp_server.py` — exposes 4 typed MCP tools over stdio. Registered globally via `make mcp-install-global`. Delegates to `execute_text()`. | *MCP*, *MCP tools*, *stdio server* |
| **Usage Metering** | Middleware (`middleware/usage.py`) enforcing per-user plan limits: Free (5 tailors/month), Pro (unlimited). Checks before and increments after each `/resume/tailor` call. | *usage limit*, *rate limit*, *plan enforcement* |
| **ATS Score Band** | Thresholds applied after scoring: `≥0.80` → Strong match (proceed), `0.60–0.79` → Good match (proceed with caveats), `0.50–0.59` → Borderline, `<0.50` → Decline (no `.tex` produced). | *score band*, *match band*, *relevance band* |
| **Regression Tests** | Test files named `_regression` (e.g., `test_profile_extractor_regression.py`) that capture behavioral quirks as characterization tests. Change only deliberately — they document intentional oddities. | *characterization tests*, *regression suite* |

---

## 6. LLM / AI Enrichment

| Canonical Term | Definition | Aliases to Avoid |
|---|---|---|
| **AI Enrichment** | An optional pass that calls the Claude API (`_enrich_profile_with_claude()`) to rewrite low-confidence Bullets into the Bullet Formula. Tags rewritten Bullets as `evidence_source=ai_enrichment`. | *LLM rewrite*, *Claude pass*, *enrichment* |
| **`_parse_with_claude()`** | Lower-level function that calls the Claude API to parse an unstructured blob into a structured Profile dict when heuristic parsing fails. | *Claude parser*, *AI parser* |
| **ANTHROPIC\_API\_KEY** | Environment variable that gates AI Enrichment. No key → enrichment silently skipped. | *API key*, *Claude key*, *LLM key* |
| **ai\_enrichment** | The `evidence_source` value set on any Bullet that was created or rewritten by the LLM. | *AI source*, *LLM source* |

---

## 7. Streamlit App

| Canonical Term | Definition | Aliases to Avoid |
|---|---|---|
| **Profile Tab** | The Streamlit tab for uploading/pasting a resume and viewing the parsed Profile as JSON. | *parse tab*, *upload tab*, *input tab* |
| **Tailor Tab** | The Streamlit tab for pasting a JD, running gap analysis, and downloading the tailored `.tex` output. | *gap tab*, *output tab*, *generate tab* |
| **Input Method** | Toggle between `Upload file` and `Paste text` modes in the Profile Tab. | *input mode*, *source mode* |
| **pdfminer Warning** | The `st.warning()` shown in the Profile Tab when `pdfminer.six` is not installed, alerting the user that PDF extraction quality is degraded. | *dependency warning*, *pdfminer alert* |
| **session\_state** | Streamlit's `st.session_state` dict used to persist `profile_dict` and `profile_text` across tab interactions. | *state*, *app state*, *Streamlit state* |

---

## 8. Test Infrastructure

| Canonical Term | Definition | Aliases to Avoid |
|---|---|---|
| **Tracer E2E Test** | End-to-end integration test (`test_tracer_e2e.py`) that runs the full Pipeline on a sample blob and JD, verifying the `.tex` output contains expected role titles and contact fields. | *integration test*, *E2E test* |
| **conftest.py** | Pytest configuration and shared fixtures. Also extends `sys.path` so tests import from the scripts directory. | *test config*, *fixtures file* |
| **sys.modules mock** | The pattern `monkeypatch.setitem(sys.modules, "anthropic", MagicMock())` used to inject a fake `anthropic` module without installing the package. Avoids `ModuleNotFoundError` in CI. | *module mock*, *anthropic mock* |
| **Coverage Gate** | `--cov-fail-under=80` in CI; a failing build if statement coverage drops below 80%. | *coverage threshold*, *coverage floor* |

---

## 9. Vocabulary for Gap Signal Categories

| Signal Category | Core Keywords |
|---|---|
| `testing_ci_cd` | pytest, unit tests, integration tests, GitHub Actions, CI/CD, coverage |
| `data_quality_observability` | data quality, schema enforcement, Great Expectations, Monte Carlo, monitoring |
| `orchestration` | Airflow, Dagster, DAGs, backfill, retries, SLA |
| `semantic_layer_governance` | dbt, metrics layer, lineage, RBAC, data contracts, single source of truth |
| `architecture_finops` | Delta Lake, Iceberg, partitioning, compaction, cost optimisation, table format |
| `streaming_realtime` | Kafka, Kinesis, event streaming, low latency, throughput, watermark |
| `ml_ai_platform` | MLflow, feature store, LLM, RAG, embeddings, model registry |
| `cloud_infra` | AWS, Azure, GCP, Kubernetes, Terraform, Docker, IaC |
| `leadership_ownership` | mentoring, cross-functional, stakeholder, roadmap, ownership, on-call |
| `sql_data_modeling` | data warehouse, dimensional modeling, OLAP, OLTP, star schema, surrogate key |

---

## 10. Flagged Ambiguities

| Ambiguous Term | Problem | Resolution |
|---|---|---|
| *resume* | Used both for the raw input file and the parsed Profile object. | Use **Artifact** for the input file; **Profile** for the parsed object. Never use *resume* for the in-memory data model. |
| *gap* | Sometimes means a single missing keyword; sometimes a whole Signal Category with low coverage. | Use **Keyword Gap** for a missing token; use **GapSignal** for a missing category. |
| *parse* | Overloaded: `parse_blob()`, `parse_pdf()`, `parse_latex()`, etc. each parse a different Format. | Always qualify: *parse blob*, *parse PDF*, *parse LaTeX*. Never say just "parse the resume" — specify the Format. |
| *score* | Used for ATS Score Estimate, Bullet confidence, and Signal priority. Three separate concepts. | Use **ATS Score Estimate** (0–100), **confidence** (`high/medium/low` on Bullet), and **priority** (`high/medium/low` on GapSignal). |
| *tier* | Can mean extraction tier (PDF parsing) or phase (project phases). | **Extraction Tier** for PDF; **Phase** for project milestones. |
| *enrichment* | Colloquially used for both Claude parsing failures and Claude rewriting. | **AI Enrichment** = Claude rewrite pass on existing Bullets. **`_parse_with_claude()`** = Claude as parser fallback when heuristics fail. Distinct operations. |
| *format* | Means both the Artifact Format (`blob`, `pdf`, etc.) and LaTeX output formatting. | **Format** = input Artifact type. **Render** = producing formatted LaTeX output. |

---

## 11. Example Dialogue Using Terms Precisely

> **Dev A**: "The user uploaded a PDF and the Profile only has one Role — the other two are missing."
>
> **Dev B**: "Which Extraction Tier ran?"
>
> **Dev A**: "Tier 2 — pypdf is installed in the Streamlit env, so pdfminer didn't run."
>
> **Dev B**: "Then the OT1 Artifacts weren't cleaned before reaching `_parse_plain_resume_text()`. The CMR bullet decoded as `ffi`, so `_is_bullet_line()` didn't recognise those lines as Bullets — they got absorbed into the company field of the preceding Role."
>
> **Dev A**: "Right. And the confidence on the Bullets we *did* extract?"
>
> **Dev B**: "All `low` — no metrics survived. The Suggested Angles for the `architecture_finops` GapSignal should prompt the user to add numbers."
>
> **Dev A**: "After OT1 Normalization runs, `_parse_plain_resume_text()` should see three Roles with evidence\_source `pdf_upload`. Then AI Enrichment can rewrite the low-confidence Bullets and tag them `ai_enrichment`."

---

*Last updated: 2026-04-06. Merge new findings by running `/ubiquitous-language` in Claude Code. Auto-invoked at session start and after auto-compact via hooks.*
