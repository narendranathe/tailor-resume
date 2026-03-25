---
name: tailor-resume
description: Builds and iteratively refines ATS-optimized, recruiter-readable, single-page resumes tailored to a target job description. Use when user asks to tailor/build/improve a resume, align experience to a job, generate LaTeX/PDF output, extract achievements from LinkedIn, GitHub, or a work history blob, or run a skills gap analysis. Loops until acceptance criteria pass. Never fabricates — only reframes factual evidence.
---

# tailor-resume

## Quick start

Ask the user for:

1. **Job Description** — paste JD text
2. **Experience artifacts** — one or more of:
   - **Attach a PDF or image file** directly to this conversation (Claude reads it natively — handles scanned PDFs, screenshots, image-based resumes, any format; see Tier 0 below)
   - Paste a **work experience blob** (free-form text describing roles, projects, outcomes)
   - Upload/paste current resume (`.tex`, `.md`, `.pdf`, `.docx` text)
   - Upload/paste **LinkedIn PDF export** text
   - Share **GitHub repo URLs** (analyze READMEs and project descriptions)
   - Share Claude project artifacts
3. **Target context** (optional): target role, company, seniority, location

No personal data is hardcoded in templates — everything is runtime-only.

---

## Workflow

### Step 0 — ATS Relevance Gate (run BEFORE anything else)

Run a first-pass ATS scan of the JD against the candidate profile. Use keyword overlap and taxonomy category coverage to estimate an initial score.

| Initial ATS | Role relationship | Action |
|---|---|---|
| ≥ 80 | Same / closely matching role | Proceed — iterate aggressively, **target 97–100** |
| 60–79 | Different title, overlapping responsibilities | Proceed — **90+ is the acceptable ceiling** |
| 50–59 | Partial overlap | Proceed with honest gap note; report ceiling |
| **< 50** | Non-overlapping role | **Do not generate.** Respond: *"This role doesn't align with your profile (initial ATS: X/100). The responsibilities don't overlap enough to produce a credible resume — generating one would require fabrication. If you believe it's relevant, clarify the connection."* |

**Irrelevant JD accumulation rule:** If the user submits 3 or more consecutive JDs each scoring < 50, respond: *"These job descriptions don't align with your profile. Please paste a Data Engineering, ML Engineering, Analytics Engineering, or related role."* Reset the counter when a relevant JD is received.

**Frequency rule:** The "not relevant" response must not fire more than 1 time in 10 invocations. If you've already declined once recently, lower your threshold by 10 points before declining again.

**Honest ceiling rule:** When the ATS score is capped by genuine technology gaps (skills the candidate has never used), report this explicitly at the end of Pass C:
> *"Optimized ATS: X/100. Honest ceiling for this JD: ~Y — [tech A, tech B] appear in the JD but are absent from your authentic experience. Resume is maximized to the highest credible level without fabrication."*

---

### Step 1 — Intake & normalization

Parse all provided artifacts into a canonical profile JSON:
```json
{
  "experience": [],
  "projects": [],
  "skills": [],
  "education": [],
  "certifications": []
}
```

Each bullet is tagged with:
- `evidence_source`: where it came from (blob, resume, LinkedIn, GitHub)
- `confidence`: high / medium / low

**Extraction tiers (auto-selected by input format):**
- **Tier 0** — Claude vision/document API: attach any PDF or image directly to the conversation. Claude reads it natively — handles scanned PDFs, image-based resumes, screenshots, and any PDF that text extractors mangle. Requires `ANTHROPIC_API_KEY`. Use `scripts/claude_vision_extractor.py`.
- **Tier 1** — pdfminer.six: best for LaTeX/CMR-font PDFs (`pip install pdfminer.six`)
- **Tier 2** — pypdf: fast for Word-generated PDFs (`pip install pypdf`)
- **Tier 3** — stdlib fallback: pure Python, zero dependencies

**Input handling guide:**
| Input type | What to extract |
|---|---|
| PDF/image attachment (Tier 0) | Use Claude vision extraction — reads file directly, returns full structured profile. Handles scanned, image-based, and garbled PDFs. |
| Scanned or image PDF | Always use Tier 0 — text extractors fail on these; Claude vision handles them perfectly. |
| Work blob | roles, companies, dates, outcomes, tools, scale signals |
| LaTeX resume | parse `\resumeItem` and `\resumeSubheading` blocks |
| Markdown resume | parse `##`, `-` bullet lists by role |
| LinkedIn PDF text | job titles, dates, descriptions per role |
| GitHub repos | README project names, tech stack, outcomes |

Ask targeted follow-up questions only when critical metrics are absent.

---

### Step 2 — JD decomposition + company research

Extract and rank from the JD:
- Must-have qualifications (MQs) — every MQ must be **explicitly visible** in the resume; never assume the reader will infer it
- Core responsibilities
- Domain/tool signals
- Seniority, leadership scope, team size expectations
- Business outcome expectations

**Company research integration:** Before generating bullets, align language with the company's known values and voice. Echo the JD's specific phrasing where authentic. Reflect the company's mission or recent focus areas in the summary's forward-looking sentence.

Output: **top 5 missing or weak signals** in the user's profile.

---

### Step 3 — Gap closure (factual integrity only)

For each gap:
- Suggest 1–2 achievement angles grounded in the provided evidence.
- If a metric is missing, ask targeted prompts:
  - "What was the baseline → outcome?"
  - "What was the scale? (rows/day, users, dollars, latency, incidents)"
- **Never invent numbers.** Range phrasing allowed only if user confirms.
- For employment gaps: address subtly with freelance work, projects, or education.
- For title mismatches: standardize to the nearest market-recognized equivalent.

---

### Step 4 — Resume rewriting rules

**Single page — no exceptions.** Every line must earn its place.

**Bullet formula:** `Accomplished [X] as measured by [Y], by doing [Z].`
- X = outcome or achievement
- Y = quantitative measure (%, $, latency, count, ratio)
- Z = specific action or method

**Per-bullet rules:**
- Lead with a strong action verb (no "I")
- Quantify wherever possible — never leave "optimized pipelines" without the %
- Be specific about what was built, why, and how success was measured
- 4–6 bullets per role maximum
- For leadership roles: include team size and scope

**Career progression:**
- Show trajectory, not just activity — level changes, scope expansions, ownership growth
- Standardize internal/uncommon titles to market-recognized equivalents (e.g., "Technical Staff Engineer" → "Senior Software Engineer")
- Each role should demonstrate advancement, not just presence

**Skills section:**
- Do NOT keyword-stuff the skills section
- Integrate keywords naturally into bullets where they make contextual sense
- Only list skills the candidate can speak to confidently in an interview
- Group logically: Languages, Data & Cloud, ETL/Modeling, Governance, Tools, DevOps

---

### Step 5 — ATS + recruiter checks

**ATS formatting requirements:**
- Standard section headers: Summary, Experience, Projects, Skills, Education
- Bold job titles and company names; consistent date formats (e.g., `Jan 2022 – Dec 2023`)
- Standard fonts — no decorative fonts
- No tables, text boxes, headers/footers that ATS cannot parse
- No multi-column layouts for core content
- Keywords appear **in context**, not as a bare list — ATS parses context too; shallow keyword drops can hurt more than help
- Use ATS-parsable LaTeX or clean DOCX

**Recruiter checks:**
- Strongest role-fit evidence in top 1/3 of the page
- Quantified impact in most bullets
- Clear career progression and scope signals
- No vague claims: every bullet has a concrete outcome or scope signal

**Red flags to address:**
- Generic bullets → replace with specific, quantified achievements
- Title mismatch → align to standard industry equivalent
- Responsibilities listed without outcomes → add the result

---

### Step 6 — Output (produce in this order)

1. Skills gap analysis (bulleted list: top 5 gaps, 1–2 adaptation angles each)
2. Tailored experience bullets per role
3. Professional summary (4–5 sentences):
   - Sentence 1: years of experience + domain + unique value proposition
   - Sentences 2–3: 2 quantified highlights from the most relevant roles
   - Sentence 4: 3–4 JD keywords integrated naturally (not stuffed)
   - Sentence 5: forward-looking statement about contributing to **this specific company/role**
4. Final single-page LaTeX (`resume.tex`) using `templates/resume_template.tex`
5. PDF export instructions (see `scripts/pdf_export.md`)

---

### Step 7 — Iterative loop (max 3 passes)

- **Pass A**: full draft
- **Pass B**: tighten relevance, fill missing metrics, densify authentic JD keyword coverage
- **Pass C**: compress for strict one-page fit; verify checklist below

**Pre-finalization checklist (verify before declaring done):**
- [ ] Single page — no exceptions
- [ ] Summary is 4–5 sentences, ends with a role-specific forward-looking statement
- [ ] At least 2–4 bullets demonstrate testing, CI/CD, or deployment ownership
- [ ] At least 2 bullets show reliability signals (resilience, schema drift, incident reduction, uptime SLA)
- [ ] At least 1–2 bullets show architecture trade-offs with cost or performance reasoning
- [ ] If Spark is listed: performance concepts are backed by examples (partitioning, shuffle, broadcast)
- [ ] Orchestration shown in production context (dependency management, retries, backfills — not just tool names)
- [ ] Data quality and observability implementation is demonstrated (not just mentioned)
- [ ] Semantic layer / metrics governance work is present if role involves BI or AI readiness
- [ ] Every bullet is quantified or has a concrete outcome
- [ ] No vague claims without metrics
- [ ] No hardcoded PII in base template
- [ ] Top JD MQs explicitly reflected
- [ ] Zero fabricated claims
- [ ] ATS meets threshold: **97+** for same role, **90+** for overlapping role

Stop early when all checklist items are satisfied.

---

### Step 8 — 2026 Role-Specific Standards

Apply the relevant phase(s) based on the target role. For **Data Engineering** roles apply all 4 phases:

**Phase 1 — Software Craftsmanship**
Show engineering rigor, not just syntax:
- Modular, testable code: Pytest, CI/CD, GitHub Actions
- Containerization for reproducibility: Docker, Kubernetes
- Resilience patterns: retries, idempotency, schema drift handling, dead-letter queues
- Quantify: incident reduction %, deployment frequency, MTTR

*Signal keywords:* `unit tests, integration tests, CI/CD, Docker, error handling, retries, idempotency, backoff, dead-letter queues, incident reduction, audit readiness`

**Phase 2 — AI Infrastructure & Semantic Layers**
Show platform thinking, not AI tool usage:
- Governed semantic layer / metrics definitions (single source of truth)
- Standardized business logic in the warehouse / lakehouse
- Workload isolation protecting production from training compute
- LLM-ready, curated, retrieval-ready datasets

*Signal keywords:* `semantic layer, governed metrics, workload isolation, schema drift, backward compatibility, retrieval-ready datasets, LLM-ready metrics, single source of truth`

**Phase 3 — Architecture & FinOps**
Defend trade-offs — strategy beats syntax:
- Architecture decisions tied to business needs (latency vs. cost vs. freshness)
- Concrete cost/performance wins ($ saved, % compute reduction, query latency improvement)
- Deep Spark performance literacy: partitioning, shuffle, broadcast joins
- Open table formats: Delta Lake, Iceberg

*Signal keywords:* `FinOps, cost optimization, TCO, partitioning, compaction, Delta Lake, Iceberg, RBAC, lineage, governance`

**Phase 4 — Orchestration & Data Quality**
Show production ownership, not hobby DAGs:
- Dependency management, retries, backfills, SLAs
- Data contracts, schema enforcement, observability
- Monitoring: freshness checks, volume checks, null rates, anomaly detection

*Signal keywords:* `Airflow, Dagster, Databricks Jobs, DAGs, backfills, SLAs, data contracts, schema enforcement, observability, Monte Carlo, Great Expectations`

---

### Step 9 — RAG persistence (optional)

To save the profile for future tailoring sessions without re-uploading:
- Embed the canonical profile JSON and store in Pinecone (or SQLite fallback).
- Use `scripts/rag_store.py` for implementation.
- On future runs, retrieve the stored profile to skip re-ingestion.

---

## Anti-patterns (never do)

- Vague claims without metrics: "optimized pipelines", "improved performance" — always add the number
- Listing tools without a story of impact — tool names are not achievements
- AI buzzwords without platform fundamentals (quality, governance, cost, reliability)
- Keyword stuffing in the skills section
- Listing responsibilities without outcomes
- Team leadership without team size or scope
- Projects without outcomes or measurements
- Generic professional summary that could apply to anyone
- Fabricating numbers, tools, or responsibilities not in the candidate's history

---

## Data handling
- User PII is **runtime-only** — never embedded in templates or committed to the repo.
- Profile embeddings stored only with explicit user consent.
- Supports full regeneration from scratch on request.

## Advanced features
See [REFERENCE.md](REFERENCE.md) — 2026 resume philosophy, 4-phase framework, bullet scoring rubric, metric prompts.
See [EXAMPLES.md](EXAMPLES.md) — example invocations and blob formats.
See `scripts/` — deterministic helpers for extraction, gap analysis, rendering, RAG, and PDF export.
See `scripts/claude_vision_extractor.py` — Tier-0 vision-based extraction for any PDF or image (scanned, image-based, screenshot).
See `templates/cover_letter_template.tex` — companion cover letter template with identical ATS-safe header style.
