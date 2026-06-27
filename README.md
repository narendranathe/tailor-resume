# tailor-resume

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://tailor-resume-ai.streamlit.app/)
[![CI](https://github.com/narendranathe/tailor-resume/actions/workflows/ci.yml/badge.svg)](https://github.com/narendranathe/tailor-resume/actions/workflows/ci.yml)

Paste a job description and your work history. The tool scores your resume against the role, identifies what is missing, rewrites your bullets, and produces a single-page LaTeX file ready to compile or upload to Overleaf.

It does not fabricate. If a metric is missing, it asks you for one. If the role does not match your profile, it tells you instead of generating a weak resume.

---

## Three ways to use it

**Browser — no install required**

Open the [Streamlit app](https://tailor-resume-ai.streamlit.app/), paste your job description and resume, and download `resume_tailored.tex`. Upload to Overleaf and export as PDF.

**Claude Code skill — interactive**

```
/tailor-resume
```

Gap analysis runs first. Bullets are rewritten across three passes. The ATS score is printed after each pass.

**CLI or Python — scripted**

```bash
python .claude/skills/tailor-resume/scripts/cli.py \
  --jd jd.txt \
  --artifact resume.md:blob \
  --name "Jane Smith" --email "jane@example.com" \
  --output out/resume.tex
```

```python
from tailor_resume import run_pipeline

result = run_pipeline(
    jd_text=open("jd.txt").read(),
    artifact_text=open("resume.md").read()
)
# result["ats_score"], result["output_path"]
```

---

## What you get

Each run produces the following:

- **Gap analysis.** The exact skill categories the job requires that your resume does not demonstrate.
- **ATS score.** A 0 to 100 estimate based on keyword overlap, category coverage, bullet quality, and seniority signals.
- **Rewritten bullets.** Each bullet follows the format `[Action verb] [what] by [method], [metric]` and is capped at 20 words.
- **Professional summary.** Four to five sentences aligned to the job description, ending with a role-specific statement.
- **resume.tex.** A single-page LaTeX file ready for `pdflatex` or Overleaf.

---

## Install

```bash
# Install via pip, no clone needed
pip install tailor-resume

# Or clone locally for development or global skill setup
git clone https://github.com/narendranathe/tailor-resume
cd tailor-resume
pip install -r requirements.txt
make install-global   # registers /tailor-resume in Claude Code and installs MCP tools globally
```

To export to PDF, run `pdflatex resume.tex` locally, or upload the `.tex` file to [Overleaf](https://www.overleaf.com). No local LaTeX installation is needed for the Overleaf path.

---

## How it is designed

- **One page, always.** The single-page constraint forces you to prioritize. It is not a limitation.
- **No fabrication.** Your experience is reframed at its strongest honest angle. Nothing is invented.
- **Honest ceiling.** If you have never used a required technology, the score reflects that. The tool says so rather than inflating the number.
- **No setup required.** The core pipeline uses Python's standard library only. Cloud features like Pinecone, OpenAI, and the Claude API are opt-in.
- **No PII in templates.** Name, email, and phone are passed at runtime and never committed to any file.

---

## Status

| | Feature | Notes |
|---|---|---|
| ✅ | Core pipeline (parse, gap analysis, render) | Standard library only, 458+ tests |
| ✅ | `/tailor-resume` Claude Code skill | Per-project and global via `make install-global` |
| ✅ | MCP plugin with 4 typed tools | stdio, auto-registered |
| ✅ | Streamlit web app | [tailor-resume-ai.streamlit.app](https://tailor-resume-ai.streamlit.app/) |
| ✅ | Hosted MCP server on Fly.io | HTTP/SSE |
| ✅ | PyPI package | `pip install tailor-resume` |
| 📋 | Docker image | [#33](https://github.com/narendranathe/tailor-resume/issues/33) |
| 📋 | FastAPI backend and React UI | [#34](https://github.com/narendranathe/tailor-resume/issues/34), [#35](https://github.com/narendranathe/tailor-resume/issues/35) |
| 📋 | Chrome extension, autoapply-ai, JobScout | [#36](https://github.com/narendranathe/tailor-resume/issues/36) to [#38](https://github.com/narendranathe/tailor-resume/issues/38) |
| 📋 | Supabase persistence, cover letter, Stripe tiers | [#39](https://github.com/narendranathe/tailor-resume/issues/39) to [#41](https://github.com/narendranathe/tailor-resume/issues/41) |

---

## Learn more

- [ARCHITECTURE.md](ARCHITECTURE.md) covers the data flow, ATS formula, file structure, design decisions, and a log of production errors and fixes.
- [CONTRIBUTING.md](CONTRIBUTING.md) covers dev setup, test commands, the PRD process, and how to file feedback.
- [UBIQUITOUS_LANGUAGE.md](UBIQUITOUS_LANGUAGE.md) is the canonical term glossary used across code, tests, and docs.
- [Open issues](https://github.com/narendranathe/tailor-resume/issues) shows the current backlog.
