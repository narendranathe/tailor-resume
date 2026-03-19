# I built a resume tailoring tool with Claude Code. Here's exactly what it does.

I've hired career coaches. Paid for resume reviews. Manually tailored resumes to job descriptions for hours at a time.

Most of the advice I got was the same: use keywords from the JD, quantify your bullets, keep it to one page. Correct advice. But the work of actually doing it, for every application, is where people give up or get lazy.

So I automated the part that's just mechanical.

**What the tool actually does**

You paste a job description. You paste your work history: free-form text, existing resume, LinkedIn PDF, GitHub links, whatever you have. It runs three things.

First, gap analysis. It maps the JD against 10 signal categories and tells you which ones your profile is weak on. Not vague feedback but specific categories like "data quality + observability," "CI/CD ownership," "FinOps + architecture trade-offs." For each gap it surfaces 1-2 achievement angles from your own experience you should be using.

Second, bullet rewrites. Every bullet gets rewritten to the "Accomplished X as measured by Y by doing Z" pattern with JD keywords integrated naturally. Up to 6 bullets per role. It asks for metrics if they're missing. It doesn't invent them.

Third, LaTeX output. One page. Standard Jake Gutierrez template, the one that parses cleanly through ATS. You compile it with `pdflatex` or upload to Overleaf.

It loops up to three passes: draft, tighten metrics, compress to one page. It stops when the output passes its own acceptance checklist.

**Why LaTeX**

ATS systems parse text. A Word doc with tables, text boxes, or custom columns will silently drop content. LaTeX with standard headings renders to a PDF where every character is selectable, which means every character is parseable. The test is simple: export to PDF and try to select text. If it selects cleanly, ATS can read it.

**The gap analysis framework**

The analyzer uses four categories that reflect what's actually valued in data engineering hiring right now.

*Software craftsmanship.* Tests, CI/CD, containerization, idempotency, incident reduction. A 2026 data engineer is expected to write software that survives schema changes and API failures without 2am pages.

*AI infrastructure.* Semantic layer, governed metrics, workload isolation. Most AI projects fail at the data layer, not the model layer. The people building the plumbing, consistent metric definitions and retrieval-ready datasets, are what the role actually needs.

*Architecture and FinOps.* Cost wins, open table formats, partition pruning. If you list Spark but can't defend your join strategy, it's a liability. The tool prompts for the trade-off story.

*Orchestration and data quality.* Production Airflow ownership, backfill strategy, data contracts, observability. Cron jobs are not acceptable at scale. Bad data triggering automated decisions is a real cost.

For each category the tool scores your resume coverage (0-100%), surfaces which JD keywords are missing, and gives you concrete prompts to fill the gap from your own experience.

**The bullet scoring rubric**

Six dimensions, 0-2 each: action clarity, business impact, metric specificity, technical depth, JD relevance, concision. Target is 9+/12 on your three most important bullets. The tool applies this on every pass.

**How it was built**

This was built in one Claude Code session using a five-skill pipeline:

- `/write-a-prd` wrote a full PRD as a GitHub issue (Issue #1)
- `/prd-to-issues` decomposed it into 7 vertical slice issues in dependency order
- `/improve-codebase-architecture` ran three sub-agents in parallel, each proposing a different architecture, and produced RFC Issue #8
- `/tdd` wrote 19 tests failing first, then implemented, and caught a real bug in the CLI entry point where `__main__` was running a hardcoded smoke test instead of the argparse CLI
- `/write-a-skill` iterated the skill instructions from a reference document

The architecture review found that all four scripts were sharing data through untyped `Dict` access with `.get()` everywhere, meaning a field rename silently broke things downstream. The RFC documents a refactor to add `resume_types.py` and `text_utils.py` as shared modules. That work is still open.

**Fork it**

```bash
git clone https://github.com/narendranathe/tailor-resume.git
cd tailor-resume
pip install -r requirements.txt
python -m pytest tests/ -v
```

19 tests, all green, no API keys required.

The skill activates automatically when you open the folder in Claude Code. Copy `.claude/skills/tailor-resume/` to `~/.claude/skills/` to make it available globally.

6 open issues. Apache 2.0. Issue #1 is the parent PRD, read it before picking anything up.

The core scripts run on Python stdlib. No cloud account required for the full pipeline. Pinecone and OpenAI are optional, there's a local SQLite fallback for profile persistence that works out of the box.
