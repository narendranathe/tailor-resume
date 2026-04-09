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
| **Extraction Tier** | One of four ordered PDF parsing strategies. Tier 0 wins; others are fallbacks. | *fallback*, *strategy*, *method* |
| **Tier 0 (Claude document API)** | *(new)* Sends raw PDF bytes directly to Claude via the Anthropic document API (`_parse_pdf_with_claude_document_api()`). Claude reads the visual layout natively — no text extraction required. Handles scanned/image-only PDFs, multi-column layouts, and garbled CMR fonts. Returns `None` on any failure so `parse_pdf()` falls through silently. Requires `ANTHROPIC_API_KEY` + `anthropic>=0.27`. | *Claude PDF parser*, *document API tier*, *native PDF reader* |
| **Tier 1 (pdfminer)** | `pdfminer.six` — reads ToUnicode CMap; best for LaTeX/CMR fonts and multi-column layouts. | *pdfminer extractor*, *primary extractor* |
| **Tier 2 (pypdf)** | `pypdf` — fast; best for Word-generated PDFs. Does not read ToUnicode CMap. | *pypdf extractor*, *secondary extractor* |
| **Tier 3 (stdlib)** | Pure-Python PDF parser; no external dependencies; used only when Tiers 1 and 2 are unavailable. | *stdlib extractor*, *fallback extractor*, *last resort* |
| **OT1 Artifact** | A garbled character produced when a Tier 2/3 extractor decodes a LaTeX CMR-font glyph without a ToUnicode CMap. The CMR bullet (0x0F) decodes as `"ffi"`; icon-font glyphs decode as `"j"`. | *encoding artifact*, *glyph corruption*, *ffi prefix* |
| **OT1 Normalization** | The post-processing pass (`_normalize_ot1_artifacts()`) that converts OT1 Artifact prefixes to real bullet characters (•) and drops lone icon lines. Applied to all tiers in `parse_pdf()`. | *glyph fix*, *encoding fix*, *OT1 cleanup* |
| **merge\_profiles()** | Combine two or more parsed Profiles into one canonical Profile, de-duplicating Roles by company+date. | *merge*, *combine*, *union profiles* |
| **auto\_detect\_format()** | Heuristic function that infers the Format of an Artifact from its content without the user declaring it. | *format detection*, *auto-detect* |
| **\_build\_profile\_from\_claude\_json()** | *(new)* Shared helper that reconstructs a `Profile` from Claude's structured JSON output. Used by both `_parse_with_claude()` and `_parse_pdf_with_claude_document_api()` so both produce structurally identical Profiles. | *Claude JSON builder*, *profile reconstructor* |
| **\_CLAUDE\_JSON\_SCHEMA\_PROMPT** | *(new)* Module-level constant holding the JSON schema prompt fragment injected into every Claude API call that returns a Profile. Centralised so both Claude parsing functions stay in sync. | *schema prompt*, *Claude prompt constant* |
| **TAILOR\_PDF\_MODEL** | *(new)* Environment variable overriding the Claude model used in Tier 0 and `_parse_with_claude()`. Defaults to `claude-haiku-4-5-20251001`. Set to `claude-sonnet-4-6` for higher accuracy. | *PDF model override*, *Claude model env var* |

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
| **Bullet Formula** | *(updated)* The required structure for a Bullet: `[Action verb] [what] by [method], [metric] — ≤20 words HARD LIMIT`. STAR compliance (Action + Result minimum) is enforced; Situation and Task are embedded in the Role header, not the Bullet. | *STAR format*, *XYZ format*, *achievement template* |
| **STAR Compliance** | *(new)* Per-bullet requirement: every Bullet must have an Action verb (A) and a measurable Result (R). Situation (S) and Task (T) are implied by the Role header. A Bullet without an Action or Result fails STAR compliance. | *STAR method*, *STAR score*, *bullet quality* |
| **STAR Score** | *(new)* Integer 0–2 per Bullet: +1 for detected Action verb, +1 for detected metric/outcome. A Bullet passes at STAR score = 2. Computed by `star_validator.score_star()`. | *bullet score*, *STAR rating* |
| **truncate\_to\_limit()** | *(new)* Renderer function in `latex_renderer.py` that enforces the 20-word hard limit on every Bullet before LaTeX escaping. Walks back up to 3 words to find a natural punctuation boundary; appends `"..."` if none found. | *word truncation*, *bullet trimmer*, *20-word cap* |
| **BULLET\_WORD\_LIMIT** | *(new)* Module-level constant in `latex_renderer.py` set to `20`. The hard ceiling for Bullet word count enforced by `truncate_to_limit()`. | *word limit*, *bullet cap* |

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
| **`_parse_with_claude()`** | *(updated)* Called after successful text extraction when `ANTHROPIC_API_KEY` is set. Sends extracted text to Claude to fix garbled extraction artifacts (word splits, encoding errors). Now uses `_build_profile_from_claude_json()` for Profile reconstruction. Previously dead code — now activated in `parse_pdf()`. | *Claude parser*, *AI parser* |
| **`_parse_pdf_with_claude_document_api()`** | *(new)* Tier 0 PDF parser. Sends raw PDF bytes to Claude natively. Never raises — returns `None` on any failure. Activated before any text extraction in `parse_pdf()`. | *Tier 0 parser*, *Claude PDF API parser* |
| **ANTHROPIC\_API\_KEY** | Environment variable that gates AI Enrichment, `_parse_with_claude()`, and Tier 0 document API parsing. No key → all three silently skipped; offline fallback runs instead. | *API key*, *Claude key*, *LLM key* |
| **ai\_enrichment** | The `evidence_source` value set on any Bullet that was created or rewritten by the LLM. | *AI source*, *LLM source* |
| **ATS Compare** | *(new)* The `/compare` API endpoint and browser UI tab that runs the same JD + resume through both the formula engine and Claude-as-judge, returning side-by-side `ATSScoreResult` objects. | *compare endpoint*, *dual scoring*, *side-by-side score* |
| **ATSScoreResult** | *(new)* Dataclass returned by `ats_scorer.score()` and `_score_claude()`. Fields: `score` (0–100), `method_used` (`"formula"` or `"claude"`), `reasoning`, `recommendations`, `bullet_scores`, `formula_score`. | *score result*, *ATS result* |
| **formula engine** | *(new)* The keyword-overlap + Signal Category coverage ATS scoring path (`method_used="formula"`). Deterministic, zero API calls. One of two engines in the compare view. | *formula scorer*, *keyword scorer* |
| **Claude-as-judge** | *(new)* The Claude API ATS scoring path (`method_used="claude"`). Claude evaluates the JD-resume fit holistically. Falls back to formula on any API error (`method_used="claude (formula fallback)"`). | *Claude scorer*, *LLM scorer*, *AI judge* |

---

## 7. API Server & Browser UI (new)

| Canonical Term | Definition | Aliases to Avoid |
|---|---|---|
| **API Server** | `api_server.py` — FastAPI app binding `localhost:8080`. Exposes 6 endpoints: `/health`, `/`, `/generate`, `/score`, `/compare`, `/cover-letter`, `/ingest/github`. | *FastAPI server*, *backend server*, *web server* |
| **`/generate`** | API endpoint: JD + Artifact → ATS Score + `resume.tex` + optional `pdf_path`. Pushes to Vault if `GITHUB_VAULT_TOKEN` is set. | *generate endpoint*, *tailor endpoint* |
| **`/score`** | API endpoint: JD + resume text → ATS Score Estimate + GapReport. Formula engine only. | *score endpoint*, *ATS endpoint* |
| **`/compare`** | API endpoint: JD + resume text → side-by-side `ATSScoreResult` from both formula and Claude-as-judge. | *compare endpoint*, *dual score endpoint* |
| **`/cover-letter`** | API endpoint: JD + Artifact → 2-paragraph Cover Letter as `.txt` + `.tex`. Optional `pdf_path` if pdflatex available. | *cover letter endpoint*, *CL endpoint* |
| **`/ingest/github`** | API endpoint: GitHub username → list of Project objects extracted from public repos. | *GitHub ingester endpoint*, *repo ingest endpoint* |
| **Cover Letter** | A 2-paragraph professional letter generated by `build_cover_letter()`. Has `txt`, `tex`, `word_count`, `method_used`, `docx_path`, `pdf_path`. | *CL*, *cover*, *letter* |
| **`_compile_pdf()`** | Helper in `api_server.py` that shells out to `pdflatex` to compile a `.tex` file to PDF. Returns `(pdf_path, None)` on success, `(None, None)` when pdflatex absent, `(None, warning_str)` on failure. Never raises. | *PDF compiler*, *pdflatex runner* |
| **`compile_pdf`** | Boolean field on `GenerateRequest` (default `True`). Set to `False` to skip pdflatex and return `.tex` only. | *compile flag*, *PDF flag* |
| **`pdf_path`** | Field on `/generate` and `/cover-letter` responses: absolute path to the compiled `.pdf` file, or `null` if unavailable. | *PDF output*, *compiled PDF* |
| **`compile_warning`** | Field on `/generate` response: non-null string describing pdflatex failure when `pdf_path` is null due to a compilation error. | *PDF warning*, *compilation error* |
| **`PDFLATEX_PATH`** | Environment variable overriding the pdflatex binary location for `_compile_pdf()`. Falls back to `shutil.which("pdflatex")`. | *pdflatex env var*, *LaTeX binary* |
| **X-API-Key** | HTTP header required on all mutating endpoints. Must match `API_KEY` env var (default: `"dev-key"`). Missing or wrong → 401. | *API key header*, *auth header* |
| **Browser UI** | The 4-tab HTML interface served at `GET /`. Tabs: Resume, Cover Letter, ATS Compare, GitHub Projects. | *web UI*, *HTML UI*, *frontend* |

---

## 8. Vault & GitHub Integration (new)

| Canonical Term | Definition | Aliases to Avoid |
|---|---|---|
| **Vault** | The `narendranathe/resume-vault` GitHub repository used to persist generated `.tex` resumes. Each user gets a branch `vault/{user_id}`. | *resume vault*, *storage repo*, *version store* |
| **VaultEntry** | Dataclass returned by `push_version()`: `version_tag` (e.g., `v20260401-abc123`), `branch`, `url`, `company`, `role`. | *vault result*, *push result* |
| **push\_version()** | Function in `vault_client.py` that commits a `.tex` file to the Vault repo on the user's branch. Returns `VaultEntry` on success, `None` silently when `GITHUB_VAULT_TOKEN` not set. | *vault push*, *save to vault*, *commit resume* |
| **vault\_version** | Field on `/generate` response: the `VaultEntry.version_tag` string, or `null` when no token is set. | *vault tag*, *version tag* |
| **`GITHUB_VAULT_TOKEN`** | GitHub personal access token environment variable gating vault pushes. No token → pushes silently skipped, no error. | *vault token*, *GitHub token*, *PAT* |
| **`user_id`** | String scoping field on `GenerateRequest` and Vault operations. Determines the vault branch and profile namespace. Falls back to `email` then `"anonymous"` if not set. | *user identifier*, *tenant ID* |
| **GitHub Ingester** | `github_ingester.py` — fetches a user's public GitHub repos and converts them into Profile `Project` objects with bullets derived from descriptions and READMEs. | *repo ingester*, *GitHub fetcher* |
| **resume-rules** | Git submodule at `narendranathe/resume-rules` wired into `tailor-resume-work`. Contains shared STAR rubric, quality rules, and validators. | *rules submodule*, *quality rules repo* |
| **compile-pdf.yml** | GitHub Actions workflow in `narendranathe/resume-vault`. Triggers on pushes to `vault/**` branches, installs texlive, compiles `.tex` → `.pdf`, and commits the PDF back. | *vault PDF workflow*, *PDF compile action* |

---

## 9. Streamlit App (updated)

| Canonical Term | Definition | Aliases to Avoid |
|---|---|---|
| **Profile Tab** | The Streamlit tab for uploading/pasting a resume and viewing the parsed Profile as JSON. | *parse tab*, *upload tab*, *input tab* |
| **Tailor Tab** | The Streamlit tab for pasting a JD, running gap analysis, and downloading the tailored `.tex` output. | *gap tab*, *output tab*, *generate tab* |
| **Input Method** | Toggle between `Upload file` and `Paste text` modes in the Profile Tab. | *input mode*, *source mode* |
| **pdfminer Warning** | The `st.warning()` shown in the Profile Tab when `pdfminer.six` is not installed, alerting the user that PDF extraction quality is degraded. | *dependency warning*, *pdfminer alert* |
| **API Key Tip** | *(new)* The `st.info()` shown in the Profile Tab when `ANTHROPIC_API_KEY` is not set, informing the user that Tier 0 PDF parsing is unavailable. Non-blocking — not a warning. | *key tip*, *API tip*, *Claude tip* |
| **session\_state** | Streamlit's `st.session_state` dict used to persist `profile_dict` and `profile_text` across tab interactions. | *state*, *app state*, *Streamlit state* |

---

## 10. Test Infrastructure

| Canonical Term | Definition | Aliases to Avoid |
|---|---|---|
| **Tracer E2E Test** | End-to-end integration test (`test_tracer_e2e.py`) that runs the full Pipeline on a sample blob and JD, verifying the `.tex` output contains expected role titles and contact fields. | *integration test*, *E2E test* |
| **conftest.py** | Pytest configuration and shared fixtures. Also extends `sys.path` so tests import from the scripts directory. | *test config*, *fixtures file* |
| **sys.modules mock** | The pattern `monkeypatch.setitem(sys.modules, "anthropic", MagicMock())` used to inject a fake `anthropic` module without installing the package. Avoids `ModuleNotFoundError` in CI. | *module mock*, *anthropic mock* |
| **Coverage Gate** | `--cov-fail-under=80` in CI; a failing build if statement coverage drops below 80%. | *coverage threshold*, *coverage floor* |
| **`_make_anthropic_mock()`** | *(new)* Test helper in `test_profile_extractor.py` that injects a fake `anthropic` module returning a controlled text response. Used by both `TestParseWithClaude` and `TestParsePdfWithClaudeDocumentApi`. | *anthropic mock factory*, *mock helper* |

---

## 11. Vocabulary for Gap Signal Categories

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

## 12. Flagged Ambiguities

| Ambiguous Term | Problem | Resolution |
|---|---|---|
| *resume* | Used both for the raw input file and the parsed Profile object. | Use **Artifact** for the input file; **Profile** for the parsed object. Never use *resume* for the in-memory data model. |
| *gap* | Sometimes means a single missing keyword; sometimes a whole Signal Category with low coverage. | Use **Keyword Gap** for a missing token; use **GapSignal** for a missing category. |
| *parse* | Overloaded: `parse_blob()`, `parse_pdf()`, `parse_latex()`, etc. each parse a different Format. | Always qualify: *parse blob*, *parse PDF*, *parse LaTeX*. Never say just "parse the resume" — specify the Format. |
| *score* | Used for ATS Score Estimate, Bullet confidence, and Signal priority. Three separate concepts. | Use **ATS Score Estimate** (0–100), **confidence** (`high/medium/low` on Bullet), and **priority** (`high/medium/low` on GapSignal). |
| *tier* | Can mean extraction tier (PDF parsing) or phase (project phases). | **Extraction Tier** for PDF; **Phase** for project milestones. |
| *enrichment* | Colloquially used for both Claude parsing failures and Claude rewriting. | **AI Enrichment** = Claude rewrite pass on existing Bullets. **`_parse_with_claude()`** = Claude as parser fallback when heuristics fail. Distinct operations. |
| *format* | Means both the Artifact Format (`blob`, `pdf`, etc.) and LaTeX output formatting. | **Format** = input Artifact type. **Render** = producing formatted LaTeX output. |
| *tier* (new conflict) | Now overloaded across Extraction Tiers (0–3) and the old project-phase usage. | **Extraction Tier** always means a PDF parsing strategy (Tier 0 = Claude doc API, Tier 1 = pdfminer, Tier 2 = pypdf, Tier 3 = stdlib). **Phase** for project milestones. |
| *compile* | Means both pdflatex compilation (`_compile_pdf()`) and general code building. | **PDF Compilation** = `_compile_pdf()` producing a `.pdf` from a `.tex`. Never use *compile* alone when pdflatex is the intent. |
| *score* (extended) | Now also used for per-Bullet **STAR Score** (0–2) in addition to **ATS Score Estimate** (0–100), Bullet **confidence**, and GapSignal **priority**. | **STAR Score** = 0–2 per Bullet. **ATS Score Estimate** = 0–100 whole-resume score. **confidence** = `high/medium/low` on Bullet. **priority** = `high/medium/low` on GapSignal. Four distinct concepts. |
| *Claude parser* | Ambiguous between Tier 0 (`_parse_pdf_with_claude_document_api`) and the text-based fallback (`_parse_with_claude`). | **Tier 0** = native document API, raw bytes in, no text extraction. **`_parse_with_claude()`** = text already extracted, Claude fixes garbling. Never say "the Claude parser" without specifying which path. |

---

## 13. Example Dialogue Using Terms Precisely (updated)

> **Dev A**: "The user uploaded a scanned PDF in the Streamlit app. The Profile came back empty."
>
> **Dev B**: "Is `ANTHROPIC_API_KEY` set in the environment?"
>
> **Dev A**: "No. So Tier 0 never ran — `_parse_pdf_with_claude_document_api()` returned `None` immediately and we fell through to Tier 1."
>
> **Dev B**: "And Tier 1 — pdfminer — extracts nothing from a scanned PDF because there's no text layer. Tier 2 and Tier 3 are the same story. So we hit the `ValueError`. Did the message tell the user what to do?"
>
> **Dev A**: "It did — the new message says 'Set `ANTHROPIC_API_KEY` to enable AI-powered parsing that handles scanned documents.' Without the key, that's the Honest Ceiling."
>
> **Dev B**: "Right. Once they set the key, Tier 0 fires first. Claude reads the visual layout directly — multi-column, scanned, garbled CMR fonts, all handled in one pass. `_build_profile_from_claude_json()` reconstructs the Profile from the JSON response."
>
> **Dev A**: "What if Tier 0 succeeds but the ATS Score Estimate is 54? The ATS Relevance Gate says decline."
>
> **Dev B**: "Show the Compare view — call `/compare` to get both the formula engine result and the Claude-as-judge `ATSScoreResult` side by side. If both agree on ~54, that's a real signal gap, not a parsing problem. Surface the Suggested Angles for the weak GapSignals."
>
> **Dev A**: "And once they've revised, push to Vault via `push_version()`. The `vault_version` tag goes back in the `/generate` response so they can retrieve it later."
>
> **Dev B**: "One more thing — every Bullet in the output needs STAR Score ≥ 2 and word count ≤ 20. `truncate_to_limit()` enforces the cap at render time, but the content still needs an Action and a measurable Result before it hits the renderer."

---

*Last updated: 2026-04-08. Merge new findings by running `/ubiquitous-language` in Claude Code. Auto-invoked at session start and after auto-compact via hooks.*
