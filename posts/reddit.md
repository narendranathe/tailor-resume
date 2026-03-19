**Title: Open-sourced a resume tailoring tool: paste JD + work history, get gap analysis + LaTeX resume. No hallucinations.**

Built this because manually tailoring resumes is the same mechanical work every time and I got tired of doing it by hand.

**What it does:**

1. Paste a job description and your work history (free-form text, existing resume, LinkedIn PDF, GitHub links)
2. It runs gap analysis across 10 categories and tells you what percentage of the JD signal your resume covers and what's missing
3. Rewrites your bullets using "Accomplished X as measured by Y by doing Z" with the actual JD keywords
4. Outputs a single-page LaTeX resume using the standard Jake Gutierrez template

It doesn't make things up. Missing a metric? It asks. Can't provide one? That bullet doesn't get a fake number.

**The gap categories for DE roles:**

- Software craftsmanship: tests, CI/CD, idempotency, incident reduction
- AI infrastructure: semantic layer, governed metrics, workload isolation, LLM-ready datasets
- Architecture + FinOps: cost wins, Delta Lake/Iceberg, partition pruning, trade-off reasoning
- Orchestration: Airflow/Dagster production ownership, backfill strategy, SLAs
- Data quality: contracts, schema enforcement, observability, anomaly detection

For each gap it gives you specific prompts: "what was baseline to outcome?" and "what was the scale, rows/day, dollars, latency?" to pull the actual metric from your experience rather than leaving the bullet vague.

**How to use it:**

```bash
git clone https://github.com/narendranathe/tailor-resume.git
cd tailor-resume
pip install -r requirements.txt
python -m pytest tests/   # 19 tests, no API keys needed
```

It's a Claude Code skill. Open the folder in Claude Code and type `/tailor-resume`. Or copy `.claude/skills/tailor-resume/` to `~/.claude/skills/` for global use.

The scripts also run standalone: no Claude required for the core pipeline, all stdlib.

**One thing worth calling out:**

The LaTeX output matters. Word docs with tables or custom layouts silently drop content in ATS. The test: export to PDF and try to copy-paste text. If it selects cleanly, ATS can parse it.

Repo: https://github.com/narendranathe/tailor-resume, Apache 2.0, 6 open issues if anyone wants to contribute (CI, Makefile, broader test coverage, architecture refactor).
