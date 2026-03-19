# tailor-resume

ATS-optimized, recruiter-ready, single-page resume tailoring — powered by Claude Code.

Paste a job description and your work history. Get a tailored LaTeX resume with quantified bullets, skills gap analysis, and ATS score — in minutes. No fabrication. No templates with your name baked in.

---

## Install

```bash
git clone https://github.com/narendranathe/tailor-resume.git
cd tailor-resume
pip install -r requirements.txt
```

Verify everything works on the included sample data:

```bash
python -m pytest tests/ -v
```

19 tests should pass. No API keys required.

---

## Activate the skill in Claude Code

This repo ships as a **Claude Code skill** — a folder of instructions and scripts that Claude picks up automatically.

### Per-project (recommended — no copy needed)

If you cloned the repo, the skill is already at `.claude/skills/tailor-resume/`. Claude Code detects it automatically when you open the project folder.

Open the project in VS Code with the Claude Code extension, or run Claude Code from the repo root:

```bash
cd tailor-resume
claude
```

The skill appears in Claude's available skills list immediately.

### Global install (use from any project)

Copy the skill folder into Claude Code's global skills directory:

**macOS / Linux:**
```bash
cp -r .claude/skills/tailor-resume ~/.claude/skills/
```

**Windows (Git Bash):**
```bash
cp -r .claude/skills/tailor-resume "$USERPROFILE/.claude/skills/"
```

After copying, the skill is available in every Claude Code session.

---

## Use the skill

Once activated, invoke the skill from any Claude Code chat:

```
/tailor-resume
```

Claude will ask for:
1. **Job description** — paste the full JD text
2. **Your experience** — choose one or more input formats (see below)

### Input formats

**Work experience blob (easiest):**
```
Company: DataWorks Inc
Title: Senior Data Engineer
Dates: Jan 2022 – Present

- Built governed semantic layer on Databricks, cutting metric discrepancies from 12/week to zero
- Owned CI/CD via Azure DevOps, compressing deployments from 8 weeks to 6 days
- Reengineered ETL to CDC merge upserts, cutting runtime from 45 min to 9 min and costs by 68%

Key metrics:
- Baseline: 45 min runtime → Outcome: 9 min
- Cost: $4,100/month saved
```

**Existing resume file — paste the content directly:**
- LaTeX (`.tex`) — paste raw LaTeX
- Markdown (`.md`) — paste markdown
- PDF/DOCX — paste extracted text

**LinkedIn PDF:**
Export your LinkedIn profile as PDF, paste the extracted text.

**GitHub repos:**
Share repo URLs — Claude reads READMEs and project descriptions to surface achievements.

### What Claude produces

1. **Skills gap analysis** — top 5 signals the JD requires that your resume doesn't show
2. **Tailored bullets** — rewritten per role using the `Accomplished X as measured by Y by doing Z` formula
3. **Professional summary** — 4–5 sentences, JD-aligned, no buzzwords
4. **Single-page LaTeX** — ready to compile
5. **PDF export instructions**

Claude runs up to 3 refinement passes automatically (draft → tighten metrics → compress to one page).

---

## Export to PDF

After Claude produces `resume.tex`:

**Local (requires a LaTeX distribution — [MiKTeX](https://miktex.org) or [TeX Live](https://tug.org/texlive/)):**
```bash
pdflatex resume.tex
```

**Overleaf (no install needed):**
1. Go to [overleaf.com](https://www.overleaf.com) and create a new blank project
2. Upload `resume.tex`
3. Set compiler to **pdfLaTeX**
4. Click **Recompile** → download PDF

ATS tip: verify your resume is machine-readable by selecting and copying text from the exported PDF.

---

## Use the scripts directly (no Claude required)

The scripts under `.claude/skills/tailor-resume/scripts/` are standalone Python — no installation beyond stdlib.

**Parse a work history blob into profile JSON:**
```bash
python .claude/skills/tailor-resume/scripts/profile_extractor.py \
  --input fixtures/sample_blob.txt \
  --format blob \
  --output out/profile.json
```

**Run JD gap analysis:**
```bash
python .claude/skills/tailor-resume/scripts/jd_gap_analyzer.py \
  --jd fixtures/sample_jd.txt \
  --profile out/profile.json
```

**Render LaTeX resume:**
```bash
python .claude/skills/tailor-resume/scripts/latex_renderer.py \
  --profile out/profile.json \
  --template .claude/skills/tailor-resume/templates/resume_template.tex \
  --output out/resume.tex \
  --name "Your Name" \
  --email "you@example.com" \
  --linkedin "https://linkedin.com/in/yourhandle" \
  --portfolio "https://yoursite.com"
```

**Try the full pipeline on sample data:**
```bash
mkdir -p out

python .claude/skills/tailor-resume/scripts/profile_extractor.py \
  --input fixtures/sample_blob.txt --format blob --output out/profile.json

python .claude/skills/tailor-resume/scripts/jd_gap_analyzer.py \
  --jd fixtures/sample_jd.txt --profile out/profile.json

python .claude/skills/tailor-resume/scripts/latex_renderer.py \
  --profile out/profile.json \
  --template .claude/skills/tailor-resume/templates/resume_template.tex \
  --output out/resume.tex \
  --name "Jane Smith" --email "jane@example.com" \
  --linkedin "https://linkedin.com/in/jane-smith" \
  --portfolio "https://janesmith.dev"
```

---

## Optional: RAG profile persistence

Store your profile as an embedding so future sessions skip re-ingestion.

**With Pinecone (cloud, persistent across devices):**
```bash
cp .env.example .env
# Edit .env and set PINECONE_API_KEY and OPENAI_API_KEY
pip install -r requirements-optional.txt

python .claude/skills/tailor-resume/scripts/rag_store.py \
  store --profile out/profile.json --user-id yourname
```

**Without any API keys (local SQLite fallback — works out of the box):**
```bash
python .claude/skills/tailor-resume/scripts/rag_store.py \
  store --profile out/profile.json --user-id yourname
```

Profiles are stored at `~/.tailor_resume/profiles.db`. On subsequent runs, Claude can retrieve your profile without re-uploading your resume.

---

## Run tests

```bash
# Core test suite (no API keys needed)
python -m pytest tests/ -v

# With coverage report
python -m pytest tests/ --cov=.claude/skills/tailor-resume/scripts --cov-report=term-missing
```

---

## Repo structure

```
tailor-resume/
├── .claude/skills/tailor-resume/
│   ├── SKILL.md          — skill instructions and 8-step workflow
│   ├── REFERENCE.md      — 2026 resume philosophy, bullet scoring rubric
│   ├── EXAMPLES.md       — invocation examples and blob format templates
│   ├── scripts/
│   │   ├── profile_extractor.py   — parse blobs, LaTeX, markdown, LinkedIn PDF
│   │   ├── jd_gap_analyzer.py     — JD gap analysis, ATS score, signal taxonomy
│   │   ├── latex_renderer.py      — profile dict → LaTeX resume
│   │   ├── rag_store.py           — Pinecone/SQLite profile persistence
│   │   └── pdf_export.md          — PDF export reference
│   └── templates/
│       └── resume_template.tex    — PII-free single-page LaTeX template
├── fixtures/
│   ├── sample_jd.txt              — sample Senior Data Engineer JD
│   ├── sample_blob.txt            — sample work experience blob
│   └── sample_profile.json        — pre-parsed profile for fast tests
├── tests/
│   ├── conftest.py                — shared fixtures and sys.path setup
│   └── test_tracer_e2e.py         — 19 end-to-end pipeline tests
├── requirements.txt               — pytest, ruff (core scripts use stdlib only)
├── requirements-optional.txt      — pinecone-client, openai
└── .env.example                   — documented env vars with safe defaults
```

---

## Design principles

- **No PII hardcoded** — all personal data passed at runtime, never committed
- **No fabrication** — Claude only reframes evidence you provide; never invents metrics
- **Zero-config default** — core pipeline runs on stdlib only; cloud features are opt-in
- **Single page** — forces prioritization; the constraint is the feature
- **Factual integrity** — if a metric is missing, Claude asks for it rather than guessing

---

## Contributing

```bash
# Lint
python -m ruff check .claude/skills/tailor-resume/scripts/ tests/

# Test
python -m pytest tests/ -v

# Submit a PR to main
```

See [open issues](https://github.com/narendranathe/tailor-resume/issues) for the current backlog. Issue #1 is the parent PRD — read it before picking up any issue.
