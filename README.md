# tailor-resume

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://tailor-resume-ai.streamlit.app/)
[![CI](https://github.com/narendranathe/tailor-resume/actions/workflows/ci.yml/badge.svg)](https://github.com/narendranathe/tailor-resume/actions/workflows/ci.yml)

Deterministic resume-tailoring pipeline: parse any resume format into a Profile, score it against a job description with a weighted ATS formula, rewrite bullets under a 20-word cap, render a single-page LaTeX file. Stdlib-only core, 458+ tests, `pip install tailor-resume`. It does not fabricate: if a metric is missing it asks, and if the role does not fit the profile it says so instead of inflating the score.

Supporting tool for the AutoApply AI pipeline, also usable standalone.

---

## Mechanisms

**Format-agnostic parsing.** Five input formats (blob, markdown, LaTeX, PDF, DOCX) auto-detected and parsed into one `Profile` dataclass. PDF extraction is a 4-tier chain (Claude document API, pdfminer.six, pypdf, stdlib), each tier returning `None` on failure so one bad PDF never blocks the run.

**Weighted ATS score.** `40% keyword_overlap + 30% category_coverage + 20% bullet_quality + 10% seniority_signal`, with a relevance gate that declines to generate below a score of 50. The gate is the point: a tool that always produces a resume is lying some of the time.

**OT1 normalization.** LaTeX-generated PDFs without a ToUnicode CMap decode the CMR bullet glyph as the literal string `ffi`. Every tier's output passes through `_normalize_ot1_artifacts()` so callers never see corrupt glyphs.

**Honest rendering.** Bullets are validated for STAR shape (action verb plus measurable result) and truncated to 20 words at the last punctuation boundary, at render time, so a long bullet fails visibly instead of silently breaking the PDF layout. PII is injected at runtime; templates hold `{{NAME}}` placeholders only.

---

## What broke in production

Preserved from the error log in [ARCHITECTURE.md](ARCHITECTURE.md):

- **ATS scores hard-capped at 99.** `int(score * 100)` truncates 0.999 to 99, so a perfectly matched resume could not score 100. One-character-class fix: `round()`.
- **The most important keywords scored zero.** A 3-character minimum token filter silently dropped "sql", "ml", "etl", "dag" from every keyword comparison, which are exactly the highest-signal terms in data engineering JDs. Minimum is now 2.
- **Every generated PDF was missing its summary.** `% \section{Summary}` was commented out in the template. Nobody noticed until scores plateaued, because everything else rendered fine.
- **A swallowed exception gave cancelled Stripe subscribers free Pro indefinitely.** The webhook handler caught the error and still returned HTTP 200, so Stripe never retried. Now it logs and returns 500.
- **`except Exception: pass` made cover-letter failures undebuggable.** Rate limits and code bugs looked identical. Split into `RateLimitError` (warn, fall back to template) and real exceptions (log with stack trace).

The pattern across all five: silent failure is worse than loud failure, and the fix is always to make the failure visible at the layer where it happens.

---

## Use it

**Browser:** [Streamlit app](https://tailor-resume-ai.streamlit.app/), paste JD and resume, download `resume_tailored.tex`, compile on Overleaf.

**CLI / Python:**

```bash
pip install tailor-resume

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

**Claude Code skill:** `/tailor-resume`, or `make install-global` after cloning.

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
| 📋 | Docker image, FastAPI + React UI, extension integrations | [#33](https://github.com/narendranathe/tailor-resume/issues/33) to [#41](https://github.com/narendranathe/tailor-resume/issues/41) |

---

## Learn more

- [ARCHITECTURE.md](ARCHITECTURE.md): data flow, ATS formula, design decisions, and the full production error log.
- [UBIQUITOUS_LANGUAGE.md](UBIQUITOUS_LANGUAGE.md): canonical term glossary used across code, tests, and docs.
- [CONTRIBUTING.md](CONTRIBUTING.md): dev setup, test commands, PRD process.

## License

MIT
