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
- **Never invent numbers.** Range phrasing allowed only if user confirms.

### Step 4 — Resume rewriting rules
- **Single page only.**
- Bullet formula: `Accomplished X as measured by Y by doing Z`
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

### Step 7 — Iterative loop (max 3 passes)
- **Pass A**: full draft
- **Pass B**: tighten relevance, fill missing metrics, densify authentic JD keyword coverage
- **Pass C**: compress for strict one-page fit; confirm ATS score meets threshold

Stop early when all acceptance criteria are satisfied:
- [ ] Single-page LaTeX output
- [ ] PDF-export ready
- [ ] No hardcoded PII in base template
- [ ] Top JD MQs explicitly reflected
- [ ] Every key bullet has a measurable outcome or scope signal
- [ ] Zero fabricated claims
- [ ] ATS meets threshold: **97+** for same role, **90+** for overlapping role

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
