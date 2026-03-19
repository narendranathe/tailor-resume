# tailor-resume

AI resume-tailoring skill for Claude Code and compatible agent interfaces.

## What this project does
- Ingests user artifacts (resume, JD, LinkedIn PDF, project links)
- Runs JD-to-experience gap analysis
- Rewrites quantified, recruiter-readable bullets
- Optimizes ATS readability (without keyword stuffing)
- Generates single-page LaTeX resume output
- Supports iterative refinement with factual integrity (no fabrication)

## Skill location
`/.claude/skills/tailor-resume/`

## Files
- `SKILL.md` – main skill behavior and workflow
- `REFERENCE.md` – resume philosophy and evaluation rubric
- `EXAMPLES.md` – prompts and expected outputs
- `scripts/profile_extractor.py` – deterministic parsing helpers
- `scripts/jd_gap_analyzer.py` – rule-based gap detection
- `scripts/latex_renderer.py` – fills template placeholders
- `scripts/pdf_export.md` – PDF export instructions

## Quick start
1. Provide:
   - Job description
   - Current resume (MD/TEX/PDF/DOCX or pasted text)
   - Optional LinkedIn PDF + GitHub links
2. Ask skill to:
   - identify top 5 missing/weak JD signals
   - rewrite role bullets with quantified impact
   - produce final single-page LaTeX resume
3. Export PDF from generated `.tex`.

## Design principles
- No personal info hardcoded in templates
- User PII passed at runtime only
- No fabricated achievements or metrics
- Clear, concise, role-relevant output

## Suggested future upgrades
- Pinecone/FAISS embeddings for reusable experience retrieval
- GitHub project mining for evidence extraction
- Automated quality scoring per bullet
