# PRD: tailor-resume v2 - Semantic Scoring, GitHub Vault, Cover Letter, SaaS Foundation

## Overview

tailor-resume v2 extends the existing Claude Code skill with four production-grade features: Claude-powered semantic ATS scoring with multi-engine fallback, automated cover letter generation in multiple formats, GitHub-based resume vault with per-user version history, and a FastAPI browser UI that replaces the CLI for day-to-day use. The PRD also documents the full future SaaS architecture (React dashboard, Stripe billing, B2B/B2C) so the foundation is designed to scale without a rewrite.

All decisions, rationale, and tradeoffs are persisted in `specs/README.md` (append-only journal).

## Problem Statement

The v1 skill works but has three friction points:
1. **ATS scoring is bag-of-words** - keyword overlap misses semantic fit. A resume saying "built CDC pipelines" does not match "stream processing experience" even though they are the same thing.
2. **Cover letters are manual** - the pipeline generates a resume but the cover letter is still written from scratch, wasting 30 min per application.
3. **No version history** - every resume generation overwrites the last. There is no way to go back to "the one I sent to Google last month" or compare two versions side-by-side.

The cost of not solving these: hours of manual work per application cycle, and irreversible loss of tailored resume history.

## Detailed Description

### Feature 1 - Multi-engine ATS Scoring (Option C -> B -> A)

**Primary: Option C (Claude-as-judge)**
Send JD + resume to Claude with a structured scoring rubric. Claude returns:
```json
{
  "score": 78,
  "reasoning": "Strong Spark/Kafka signal. Missing: schema drift handling, data contracts.",
  "bullet_scores": [{"text": "...", "score": 9, "feedback": "..."}],
  "recommendations": ["Add schema drift bullet to role 2", "Quantify CDC pipeline scale"]
}
```

**Automatic fallback: Option B (4-component formula)**
Triggers when: Claude rate limit hit, ANTHROPIC_API_KEY absent, or user opts out.
Current formula: `40% keyword overlap + 30% category coverage + 20% bullet quality + 10% seniority signal`.

**User-selectable: Option A (embedding cosine)**
Toggle: "Use semantic engine (embeddings)" - embeds JD and resume via text-embedding-3-small, cosine similarity -> score. No Claude calls.

**UI when SaaS exists:**
If Claude used: show side-by-side comparison (Claude result vs formula result). User picks one, edits, then downloads.

**Fallback chain (automatic):** Claude -> rate limit/error -> Option B -> always succeeds.

### Feature 2 - Cover Letter Generator

**Inputs:** profile dict, gap report, JD text, target company name, user header (name/contact).
**Output:** User-selected format at download: `.tex` (source), `.pdf` (compiled), `.txt` (plain copy-paste), `.docx` (via python-docx).

**Structure (max 250 words, 2 paragraphs):**
- Para 1: Hook - why this specific role + company. Pulls from JD signals (mission, team, product). No generic "I am writing to..." openers.
- Para 2: Impact bridge - 2-3 specific achievements from the resume that map to the top 3 JD requirements, written in compressed STAR form (not bullet points).

**Module:** `scripts/cover_letter_renderer.py` - `build_cover_letter(profile_dict, report, header, jd_text, method="claude"|"template") -> CoverLetterResult`

Visual design: Shares `resume_template.tex` font/color definitions. Same contact header block. Consistent look without copy-paste styling.

### Feature 3 - GitHub Resume Vault (Version Control for Resumes)

**Architecture: One private repo (narendranathe/resume-vault), one branch per user.**

```
resume-vault/
  Branch: vault/{user_id}/
    {Company}_{Role}_{YYYYMMDD_HHMMSS}.tex         <- LaTeX source
    {Company}_{Role}_{YYYYMMDD_HHMMSS}.pdf         <- compiled PDF (GitHub Actions)
    {Company}_{Role}_{YYYYMMDD_HHMMSS}.meta.json   <- ATS score, JD hash, engine used
```

**Git tag naming convention (from autoapply-ai):**
`{FirstName}_{Company}_{Role}[_{JobID}]`
Example: `Narendranath_Google_SeniorDE_JOB12345`

**Recruiter filename rule:** Always `{FirstName}.pdf` at download - internal tags never exposed.

**Ownership rules (non-negotiable):**
- resume-vault repo owned exclusively by narendranathe. Users never get direct GitHub access.
- All reads/writes go through the API layer (scripts/vault_client.py).
- User data deletion: branch delete + DB purge via support ticket (not self-serve).

**Why per-user branch (not per-user folder on main):**
- Isolation: delete branch = delete all user data (GDPR-clean)
- No cross-user merge conflicts
- `git log vault/{user_id}` = clean audit trail for one user
- Branch protection rules restrict pushes to system account only

**Module:** `scripts/vault_client.py` - `push_version(user_id, company, role, tex, metadata) -> VaultEntry`; `list_versions(user_id) -> List[VaultEntry]`; `get_version(user_id, tag) -> VaultEntry`

### Feature 4 - FastAPI Browser UI (Internal Tool, MVP)

Replace the CLI with a local FastAPI server + minimal HTML/HTMX interface.

**Endpoints:**
- `POST /generate` - full pipeline (JD + artifact -> ATS score + resume.tex + cover letter)
- `GET /vault/{user_id}` - list resume versions
- `GET /vault/{user_id}/{tag}` - download specific version
- `POST /score` - score JD vs resume only (no render)
- `GET /compare?a={tag}&b={tag}` - side-by-side version comparison

**Auth for MVP:** Single hardcoded API key in .env (internal only).

---

## Future SaaS Architecture (v3, not MVP scope)

### Stack
- Backend: FastAPI + PostgreSQL (Supabase) + Redis (Upstash) + Fly.io
- Frontend: React/Vite + TailwindCSS + shadcn/ui
- Auth: Clerk (RS256 JWT, same pattern as autoapply-ai)
- Billing: Stripe (subscription tiers + per-generation metering)
- Embeddings: Pinecone (already implemented in rag_store.py)

### Pricing Tiers

Token cost basis: ~$0.10/resume (Claude Sonnet, full pipeline with cover letter).
Competitive benchmark: Jobright.ai ~$19.99/mo, Simplify ~$12/mo, Kickresume ~$10/mo.
Target: 50% cheaper.

| Tier | Price | Daily limit | Rationale |
|------|-------|-------------|-----------|
| Free | $0 | 3/day | Customer acquisition; absorb ~$9/mo token cost as CAC |
| Starter | $4.99/mo | 15/day | 50% of $10 floor; covers avg 5/day user token cost |
| Pro | $9.99/mo | 50/day | 50% of $19.99 competition; 5x token cost of P50 user |
| Unlimited | $29.99/mo | 200/day rate limit | P90 user; anti-abuse cap enforced |
| API/Team | $99/mo | 1000/day rate limit | B2B/recruiters; activation requires Narendra approval |

### Anti-bot Protection

Detection signals: >20 generations in 60 minutes, after-hours bulk generation (>50 between midnight-6am local), known bot UA patterns, identical JD text submitted >10x in 5 minutes.

Response sequence:
1. Warning 1-4: Toast with counter. "This looks like bot activity. Warning {n}/4."
2. Warning 5 (first offense): 24-hour deactivation. Email sent.
3. Repeat offense (5 total deactivations): Permanent block. Admin review required to unblock.

Implementation: Redis sorted-set sliding window per user_id; evaluated at every /generate call.

### Support and Admin

**User-facing:**
- FAQ page (self-serve for top 10 ticket categories)
- Submit issue form (category + description + account info auto-populated)
- "My Account" section: download all resume versions, view usage, view warnings history

**Admin (Narendra only):**
- Internal ticket queue (/admin/tickets) - view, tag, resolve, escalate
- Account management: unblock user, reset warnings, extend tier, view vault branch
- Solutions KB: paste-in answers to common tickets

---

## User Stories

- As Narendra, I want to paste a JD and my resume blob into a browser form and get a Claude-scored ATS report + resume.tex in under 10 seconds.
- As Narendra, I want to see Claude score side-by-side with the formula score and choose which bullets to keep.
- As Narendra, I want every generated resume auto-committed to the GitHub vault so I can retrieve any past version by company and role.
- As a future job seeker (v3), I want to subscribe for $9.99/month and generate unlimited tailored resumes with cover letters.
- As Narendra (admin), I want to see all support tickets in one queue and resolve them without leaving the app.

## Acceptance Criteria

### v2 MVP
- [ ] `cover_letter_renderer.py` - `build_cover_letter()` returns CoverLetterResult with .tex, .txt, .pdf, .docx attrs; 2-paragraph structure enforced
- [ ] `scripts/ats_scorer.py` - `score(jd, resume, method)` returns ATSScoreResult; Option C fallback to Option B on exception; Option A available as explicit method
- [ ] `scripts/vault_client.py` - `push_version()` creates branch if absent, commits .tex + .meta.json; `list_versions()` returns list sorted by timestamp desc
- [ ] `scripts/github_ingester.py` - given repo URL, returns list of Bullet dicts from README + description; public repos only, no auth required
- [ ] FastAPI browser UI - `POST /generate` returns JSON with ats_score, resume_path, cover_letter_path, vault_tag
- [ ] All new modules have test coverage >= 80%
- [ ] `specs/README.md` updated with all new architectural decisions
- [ ] `python scripts/sync_global.py` propagates all changes

### v3 SaaS (future)
- [ ] Clerk auth integrated
- [ ] Stripe billing with all 5 tiers
- [ ] Anti-bot Redis sliding window
- [ ] React dashboard with side-by-side score comparison
- [ ] Admin ticket queue

## Non-Functional Requirements

- Performance: Cover letter generation <= 8s (Claude call). Resume render <= 2s (no LLM). ATS formula score <= 200ms.
- Security: No PII in templates or git history. GITHUB_VAULT_TOKEN never logged. All user data scoped by user_id.
- Reliability: Option C -> Option B fallback is automatic and silent. Vault push failure is non-blocking (pipeline still returns the resume).

## Technical Context (verified from repo)

### Existing code affected
- `scripts/pipeline.py:118` - lazy import of cover_letter_renderer already wired; just needs to be created
- `scripts/mcp_server.py` - add generate_cover_letter as 5th MCP tool
- `scripts/jd_gap_analyzer.py:195-222` - 4-component formula; wrapped as Option B inside ats_scorer.py
- `scripts/rag_store.py:_embed_openai()` - reused for Option A embedding calls
- `requirements-optional.txt` - add fastapi, uvicorn, python-docx, httpx

### Established patterns to follow
- All scripts add _SCRIPTS dir to sys.path for import portability
- Error return: `{"error": "message"}` JSON string - never raise in MCP tools
- `user_id: str = ""` default throughout all layers
- Factory pattern for backend selection: get_store() in rag_store.py; replicate as get_scorer()

## Module Breakdown

### Module 1: ats_scorer.py
- **Responsibility:** Unified ATS scoring facade - Claude (C), formula (B), embedding (A)
- **Interface:** `score(jd: str, resume: str, method: str = "claude") -> ATSScoreResult`
- **Dependencies:** jd_gap_analyzer.run_analysis (B), rag_store.embed (A), Anthropic SDK (C)
- **Complexity:** M

### Module 2: cover_letter_renderer.py
- **Responsibility:** Generate 2-paragraph cover letter, export in .tex/.txt/.pdf/.docx
- **Interface:** `build_cover_letter(profile_dict, report, header, jd_text, method) -> CoverLetterResult`
- **Dependencies:** resume_types.GapReport, latex_renderer.escape, Anthropic SDK, python-docx
- **Complexity:** M

### Module 3: vault_client.py
- **Responsibility:** Read/write resume versions to resume-vault GitHub repo via REST API
- **Interface:** `push_version(user_id, company, role, tex_content, metadata) -> VaultEntry`
- **Dependencies:** httpx or urllib, GITHUB_VAULT_TOKEN env var
- **Complexity:** M

### Module 4: github_ingester.py
- **Responsibility:** Fetch GitHub repo and extract project bullets for profile
- **Interface:** `ingest_repo(url: str, token: Optional[str] = None) -> List[Dict]`
- **Dependencies:** httpx or urllib, profile_extractor.parse_blob
- **Complexity:** S

### Module 5: api_server.py
- **Responsibility:** FastAPI browser UI server (internal use, MVP)
- **Interface:** POST /generate, POST /score, GET /vault/{user_id}, GET /compare
- **Dependencies:** pipeline.execute_text, ats_scorer.score, vault_client, cover_letter_renderer
- **Complexity:** L

### Module 6: resume-rules submodule
- **Responsibility:** Shareable, versioned resume quality standards (STAR rubric, validators)
- **Interface:** Submodule at resume-rules/; star_validator.py and text_utils.py imported from submodule
- **Dependencies:** None (stdlib only)
- **Complexity:** S

## Dependency Graph

```
resume_rules/ (submodule, no deps)
        |
   +----|------------------+
   |                       |
ats_scorer(M)   cover_letter_renderer(M)   vault_client(M)
   |                       |                     |
   +----------- pipeline.py (existing) ----------+
                     |
          +----------+----------+
          |                     |
   api_server.py(L)    mcp_server.py(existing)
          |
   github_ingester.py(S, standalone)
```

Build order: resume_rules submodule -> ats_scorer -> cover_letter_renderer -> vault_client -> github_ingester -> pipeline updates -> api_server

## Out of Scope

- React/Vite frontend (v3 only)
- Clerk authentication (v3)
- Stripe billing (v3)
- Anti-bot Redis middleware (v3; MVP uses simple in-memory rate limiting)
- Multi-language resume support

## Open Questions

- GitHub Actions workflow for auto-compiling .tex -> .pdf in resume-vault?
- Rate limit backend for MVP: Redis or simple in-memory dict?
- DOCX generation: python-docx vs pandoc subprocess?
- GitHub ingestion: public repos only for MVP?
- Admin ticketing: SQLite tickets table vs Linear integration?

## Definition of Done

- [ ] All v2 MVP acceptance criteria met
- [ ] `make test` passes with >= 80% coverage including new modules
- [ ] `make lint` passes (ruff, no new violations)
- [ ] `python scripts/sync_global.py` propagates all changes
- [ ] `specs/README.md` updated with all new decisions
- [ ] CI green on Python 3.11 and 3.12
- [ ] No PII in any committed file
- [ ] Browser UI (api_server.py) serves full pipeline from localhost without CLI
