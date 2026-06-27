# tailor-resume

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://tailor-resume-ai.streamlit.app/)
[![CI](https://github.com/narendranathe/tailor-resume/actions/workflows/ci.yml/badge.svg)](https://github.com/narendranathe/tailor-resume/actions/workflows/ci.yml)

Paste a job description. Paste your work history. Get a single-page LaTeX resume — tailored to that role, scored against the ATS formula, rendered in minutes.

It doesn't fabricate. If a metric is missing, it asks. If the role doesn't match your profile, it tells you rather than producing a weak resume.

---

## Three ways in

**Browser — no install, 30 seconds**

[Open the Streamlit app →](https://tailor-resume-ai.streamlit.app/) Paste JD + resume, download `resume_tailored.tex`, upload to Overleaf.

**Claude Code — interactive, three-pass rewriting loop**

```
/tailor-resume
```

Gap analysis runs first. Bullets are rewritten three times. ATS score printed at every step.

**CLI — scripted, integrates anywhere**

```bash
python .claude/skills/tailor-resume/scripts/cli.py \
  --jd jd.txt \
  --artifact resume.md:blob \
  --name "Jane Smith" --email "jane@example.com" \
  --output out/resume.tex
```

Or via Python:

```python
from tailor_resume import run_pipeline
result = run_pipeline(jd_text=open("jd.txt").read(), artifact_text=open("resume.md").read())
# result["ats_score"], result["output_path"]
```

---

## What comes out

The pipeline reads your artifacts, scores them against the JD, and produces:

- **Gap analysis** — the exact signal categories the role requires that your resume doesn't show
- **ATS score** — 0–100 estimate across keyword overlap, category coverage, bullet quality, and seniority signal
- **Rewritten bullets** — `[Action verb] [what] by [method], [metric]` — ≤20 words, STAR-compliant, no vague claims
- **Professional summary** — 4–5 sentences, JD-aligned, ends with a role-specific forward-looking statement
- **`resume.tex`** — single-page LaTeX, ready for `pdflatex` or Overleaf

---

## Install

```bash
# Via pip — no clone needed
pip install tailor-resume

# Local clone — for development or global skill install
git clone https://github.com/narendranathe/tailor-resume
cd tailor-resume
pip install -r requirements.txt
make install-global   # adds /tailor-resume to Claude Code + registers MCP tools globally
```

Compile the output to PDF with `pdflatex resume.tex`, or drop the `.tex` file into [Overleaf](https://www.overleaf.com) — no local LaTeX install needed.

---

## Opinions

- **One page, always.** The constraint forces prioritization. It is the feature.
- **No fabrication.** Evidence is reframed at its strongest defensible angle — never invented.
- **Honest ceiling.** If you've never used a required technology, the score reflects that and says so, rather than pretending.
- **Zero-config by default.** Core pipeline runs on stdlib only. Cloud features (Pinecone, OpenAI, Claude API) are opt-in.
- **PII never committed.** Name, email, phone are injected at runtime — never hardcoded in templates.

---

## Status

| | Feature | Notes |
|---|---|---|
| ✅ | Core pipeline — parse → gap → render | stdlib only · 458+ tests |
| ✅ | `/tailor-resume` Claude Code skill | per-project + global via `make install-global` |
| ✅ | MCP plugin — 4 typed tools | stdio · auto-registered |
| ✅ | Streamlit web app | [tailor-resume-ai.streamlit.app](https://tailor-resume-ai.streamlit.app/) |
| ✅ | Hosted MCP server | Fly.io · HTTP/SSE |
| ✅ | PyPI package | `pip install tailor-resume` |
| 📋 | Docker image | [#33](https://github.com/narendranathe/tailor-resume/issues/33) |
| 📋 | FastAPI backend + React UI | [#34](https://github.com/narendranathe/tailor-resume/issues/34) · [#35](https://github.com/narendranathe/tailor-resume/issues/35) |
| 📋 | Chrome extension · autoapply-ai · JobScout | [#36](https://github.com/narendranathe/tailor-resume/issues/36)–[#38](https://github.com/narendranathe/tailor-resume/issues/38) |
| 📋 | Supabase persistence · cover letter · Stripe tiers | [#39](https://github.com/narendranathe/tailor-resume/issues/39)–[#41](https://github.com/narendranathe/tailor-resume/issues/41) |

---

## Go deeper

- [**ARCHITECTURE.md**](ARCHITECTURE.md) — data flow, ATS formula, file structure, ubiquitous language, dev stages, design decisions, errors and how we fixed them
- [**CONTRIBUTING.md**](CONTRIBUTING.md) — dev setup, test commands, PRD process, how to file feedback
- [**UBIQUITOUS_LANGUAGE.md**](UBIQUITOUS_LANGUAGE.md) — canonical term glossary
- [Open issues](https://github.com/narendranathe/tailor-resume/issues) — current backlog
