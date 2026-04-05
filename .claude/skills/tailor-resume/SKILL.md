---
name: tailor-resume
description: Builds and iteratively refines ATS-optimized, recruiter-readable, single-page resumes tailored to a target job description. Use when user asks to tailor/build/improve a resume, align experience to a job, generate LaTeX/PDF output, extract achievements from GitHub or LinkedIn, or run a skills gap analysis. Loops until acceptance criteria pass. Never fabricates — only reframes factual evidence.
---

# tailor-resume

## Quick start

Ask the user for:

1. **Job Description** — paste JD text
2. **Experience artifacts** — one or more of:
   - Paste a **work experience blob** (free-form text describing roles, projects, outcomes)
   - Upload/paste current resume (`.tex`, `.md`, `.pdf`, `.docx` text)
   - Upload/paste **LinkedIn PDF export** text
   - Share **GitHub repo URLs** (I'll analyze READMEs and project descriptions)
   - Share Claude project artifacts
3. **Target context** (optional): target role, company, seniority, location

No personal data is hardcoded in templates — everything is runtime-only.

---

## Workflow

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

**Input handling guide:**
| Input type | What to extract |
|---|---|
| Work blob | roles, companies, dates, outcomes, tools, scale signals |
| LaTeX resume | parse `\resumeItem` and `\resumeSubheading` blocks |
| Markdown resume | parse `##`, `-` bullet lists by role |
| LinkedIn PDF text | job titles, dates, descriptions per role |
| GitHub repos | README project names, tech stack, outcomes |

Ask targeted follow-up questions only when critical metrics are absent.

### Step 2 — JD decomposition
Extract and rank from the JD:
- Must-have qualifications (MQs)
- Core responsibilities
- Domain/tool signals
- Seniority and leadership scope
- Business outcome expectations

Output: **top 5 missing or weak signals** in the user's profile.

### Step 3 — Gap closure (factual integrity only)
For each gap:
- Suggest 1–2 achievement angles grounded in the provided evidence.
- If a metric is missing, ask targeted prompts:
  - "What was the baseline → outcome?"
  - "What was the scale? (rows/day, users, dollars, latency, incidents)"
- **Evidence reframing over zero fabrication.** Never invent facts or claim outcomes that didn't happen. But always reframe real evidence at its *strongest defensible angle*: claim ownership if you owned it, use the upper bound of confirmed ranges, convert "contributed to" into active impact if accurate. Understatement is not integrity — it's an ATS penalty. If a metric is missing, ask for a range; use the confirmed range in the bullet. Vague "improved performance" bullets score 0 on ATS; a confirmed "reduced latency ~40%" bullet scores fully.

### Step 4 — Resume rewriting rules
- **Single page only.**
- Bullet formula: `[Action verb] [what] by [method], [metric] — ≤20 words HARD LIMIT`
- **STAR compliance required on every bullet:** Action + Result minimum.
  Situation and Task are embedded in the role header above, not stated in the bullet (compression).
- Renderer enforces ≤20 words automatically via `truncate_to_limit()` — write compliant bullets before render.
- 4–6 bullets per role maximum.
- Strong action verbs; no keyword stuffing.
- Natural JD keyword integration.
- Standardize internal/uncommon job titles to market-recognized equivalents.
- Emphasize: progression, ownership, reliability, cost/perf wins, business impact.

### Step 5 — ATS + recruiter checks
**ATS:**
- Parsable structure (no text boxes, no decorative tables for core content)
- Standard headings: Summary, Experience, Projects, Skills, Education
- Keywords appear in context, not as pasted lists

**Recruiter:**
- Strongest role-fit evidence in top 1/3 of the page
- Quantified impact in most bullets
- Clear career progression and scope signals

### Step 6 — Output (produce in this order)
1. Skills gap analysis (bulleted list)
2. Tailored experience bullets per role
3. 4–5 sentence professional summary
4. Final single-page LaTeX (`resume.tex`) using `templates/resume_template.tex`
5. PDF export instructions (see `scripts/pdf_export.md`)

### Step 7 — Iterative loop (max 3 passes)
- **Pass A**: full draft
- **Pass B**: tighten relevance and fill missing metrics
- **Pass C**: compress for strict one-page fit

Stop early when all acceptance criteria are satisfied:
- [ ] Single-page LaTeX output
- [ ] PDF-export ready
- [ ] No hardcoded PII in base template
- [ ] Top JD MQs explicitly reflected
- [ ] Every bullet ≤20 words (renderer-enforced)
- [ ] Every bullet has a measurable Result (%, $, time, count)
- [ ] STAR score ≥2/2 for every bullet in top 3 roles
- [ ] Every claim is evidence-reframed (not fabricated, but pushed to its strongest defensible angle)

### Step 8 — RAG persistence (optional)
To save the profile for future tailoring sessions without re-uploading:
- Embed the canonical profile JSON and store in Pinecone (or SQLite fallback).
- Use `scripts/rag_store.py` for implementation.
- On future runs, retrieve the stored profile to skip re-ingestion.

---

## Data handling
- User PII is **runtime-only** — never embedded in templates or committed to the repo.
- Profile embeddings stored only with explicit user consent.
- Supports full regeneration from scratch on request.

## Advanced features
See [REFERENCE.md](REFERENCE.md) — 2026 resume philosophy, 4-phase framework, bullet scoring rubric, metric prompts.
See [EXAMPLES.md](EXAMPLES.md) — example invocations and blob formats.
See `scripts/` — deterministic helpers for extraction, gap analysis, rendering, RAG, and PDF export.
