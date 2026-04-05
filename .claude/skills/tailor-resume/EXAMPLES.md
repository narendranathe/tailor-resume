# Usage Examples

---

## Example 1 — Full tailoring from scratch
```
/tailor-resume

JD: [paste job description here]

Experience blob:
I worked at Acme Corp as a Data Engineer from July 2022 to present.
I built a governed semantic layer on our data lakehouse using DAX metrics. It cut support
tickets by ~40% and reduced query times from 12s to under 4s. I owned CI/CD end-to-end
through Azure DevOps — deployment cycles went from 3 months to 14 days. I also
re-engineered ETL from full-table reloads to CDC incremental capture, cutting runtime
from 30 min to under 8 min and compute costs by ~67%.

LinkedIn PDF: [paste extracted text here]
GitHub: https://github.com/your-username/your-project
```

---

## Example 2 — From existing LaTeX resume
```
/tailor-resume

JD: [paste job description]

Current resume (LaTeX):
\resumeSubheading{Data Engineer}{July 2022 -- Present}{Acme Corp}{City, ST}
\resumeItemListStart
  \resumeItem{Architected governed semantic layer on data lakehouse with DAX metrics...}
  \resumeItem{Compressed deployment cycles from 3 months to 14 days via Azure DevOps CI/CD...}
\resumeItemListEnd
```

---

## Example 3 — Skills gap analysis only
```
/tailor-resume

Mode: gap analysis only

JD: [paste JD]
Resume: [paste resume text]

Output: top 5 missing/weak signals + 1-2 factual achievement angles per gap
```

---

## Example 4 — ATS check only
```
/tailor-resume

Mode: ATS + recruiter check

Resume: [paste current resume]
JD: [paste JD]

Output: flag red flags and propose fixes — no fabrication
```

---

## Example 5 — Summary generation
```
/tailor-resume

Mode: summary only

JD: [paste JD]
Background: [paste key experiences / skills]

Output: 4–5 sentence professional summary with 3–4 natural JD keywords
```

---

## Example 6 — GitHub project extraction
```
/tailor-resume

I have a project at https://github.com/your-username/your-project.
Extract achievements I can use in my resume for a Senior Data Engineer role at a fintech company.
JD: [paste JD]
```

---

## Work experience blob format (template)
Use this format when pasting a work history blob:

```
Company: [Company Name]
Title: [Your Title]
Dates: [Start] – [End or Present]
Location: [City, State or Remote]

What I built / owned:
- [Project or system description with scale and tools]
- [Outcome: what improved, by how much]
- [Reliability / quality story: tests, incidents prevented, SLA]

Key metrics I can confirm:
- Baseline: [X] → Outcome: [Y]
- Scale: [rows/day, users, compute cost, etc.]
- Team size: [solo / N-person team / cross-functional]
```

---

---

## Example 7 — STAR-compliant bullet output (≤20 words each)

When rewriting bullets, every output must satisfy: Action + Result + ≤20 words.

| Input blob bullet | STAR-compliant output (≤20 words) |
|---|---|
| "Built a governed semantic layer on Azure Databricks tracking 40+ KPIs, cut support tickets by 40%" | "Governed semantic layer on Databricks: 40+ KPIs standardized, support tickets cut 40%." *(12 words)* |
| "Owned CI/CD end-to-end through Azure DevOps for 15 data pipelines, deployment went from 3 months to 14 days" | "Owned CI/CD for 15 pipelines via Azure DevOps, compressing cycles 3 months → 14 days." *(15 words)* |
| "Re-engineered ETL from full-table reloads to CDC incremental capture cutting runtime from 30 min to under 8 min" | "Migrated ETL to CDC upserts, cutting runtime 73% (30 min → 8 min) and costs 67%." *(16 words)* |

**Rules enforced by renderer:**
- Bullets >20 words are truncated at natural punctuation boundary
- `star_validator.score_star()` flags bullets missing Action or Result

---

## PDF export quick reference
```bash
# Local (requires TeX distribution — MiKTeX or TeX Live)
pdflatex resume.tex

# Overleaf (no local install needed)
# 1. Upload resume.tex and any supporting files
# 2. Set compiler to pdfLaTeX
# 3. Build and download PDF
```
