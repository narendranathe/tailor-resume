---
name: tailor-resume
description: Builds and iteratively improves a resume-tailoring skill that transforms user experience into ATS-optimized, recruiter-readable, single-page resumes aligned to a target job description. Use when user asks to create/build/improve a resume skill, tailor resumes to jobs, extract achievements from artifacts (resume/GitHub/LinkedIn), or generate LaTeX/PDF resumes with factual, quantified bullets.
---

# tailor-resume (Resume Builder + ATS Optimizer)

## Quick start
1. Ask user for:
   - Target Job Description (JD)
   - Current resume (MD/TEX/PDF/DOCX) or pasted blob
   - Optional LinkedIn PDF + GitHub repo links
2. Parse artifacts and normalize into structured profile:
   - roles, projects, outcomes, metrics, tools, domains
3. Run JD-to-profile gap analysis.
4. Generate:
   - skills-gap report
   - tailored bullets per role (4–6 max per role)
   - 4–5 sentence summary
   - ATS-safe single-page LaTeX output
5. Validate factual integrity (no fabrication) and ask targeted follow-up questions for missing metrics.

## Workflow

### 1) Intake & normalization
- Accept user data separately (never hardcode PII in templates).
- Supported inputs:
  - `.md`, `.tex`, `.docx`, `.pdf`, pasted text blobs
  - LinkedIn PDF
  - Optional GitHub/Claude project links
- Build canonical profile JSON:
  - `experience[]`, `projects[]`, `skills[]`, `education[]`, `certifications[]`
  - each bullet tagged with `evidence_source` and `confidence`

### 2) JD analysis
Extract:
- Must-have qualifications
- Core responsibilities
- Domain/tool signals
- Seniority/leadership signals
- Business outcome expectations

Rank top 5 missing/weak signals.

### 3) Gap closure with factual integrity
For each weak signal:
- Suggest 1–2 candidate achievements from user evidence.
- If metric missing, ask concise metric prompts:
  - “What was baseline → outcome?”
  - “Volume/scale? (rows/day, users, dollars, latency, incidents)”
- Never invent numbers; allow range phrasing only if user-approved.

### 4) Resume rewriting rules
- One page only.
- Bullet formula: **Accomplished X as measured by Y by doing Z**.
- 4–6 bullets/role max.
- Strong action verbs, no keyword stuffing.
- Natural JD keyword integration.
- Standardized job titles when internal title is uncommon.
- Emphasize progression, ownership, reliability, cost/perf, and business impact.

### 5) ATS + recruiter optimization checks
- ATS checks:
  - parsable layout
  - standard headings
  - no text boxes/tables for core content
  - keyword relevance in context
- Recruiter checks:
  - first 1/3 page contains strongest role-fit evidence
  - quantified impact in most bullets
  - clear progression and scope

### 6) Output generation
Produce:
1. Skills gap analysis (bulleted)
2. Tailored experience bullets
3. Role-specific summary
4. Final single-page LaTeX using provided template
5. PDF Export

### 7) Iterative refinement loop (bounded)
Run up to 3 passes:
- Pass A: draft
- Pass B: tighten relevance/metrics
- Pass C: compress for one-page fit + readability
Stop early if acceptance criteria met.

## Acceptance criteria
- Single-page LaTeX and PDF output (template-compatible)
- No embedded personal info in base template
- Every major bullet has measurable outcome or scope
- Top JD requirements explicitly reflected
- No fabricated claims

## Data handling
- User PII provided at runtime only.
- Support deletion and regeneration.
- Persist embeddings only with user consent.

## Advanced features
See [REFERENCE.md](REFERENCE.md), [EXAMPLES.md](EXAMPLES.md), and `scripts/`.