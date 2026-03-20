# tailor-resume

ATS-optimized, recruiter-ready, single-page resume tailoring — powered by Claude Code.

Paste a job description and your work history. Get a tailored LaTeX resume with quantified bullets, skills gap analysis, and ATS score — in minutes. No fabrication. No templates with your name baked in.

---

## Install

**Local (use only from this repo):**
```bash
git clone https://github.com/narendranathe/tailor-resume ~/projects/tailor-resume
cd ~/projects/tailor-resume
pip install -r requirements.txt
python -m pytest tests/ -v   # 190 tests, no API keys required
```

**Global (use `/tailor-resume` and MCP tools from any project — recommended):**
```bash
git clone https://github.com/narendranathe/tailor-resume ~/projects/tailor-resume
cd ~/projects/tailor-resume
pip install -r requirements.txt
make install-global           # copies skill, registers MCP, installs optional deps
# Restart Claude Code, then type /tailor-resume from any project
```

`make install-global` is idempotent — safe to run again after `git pull` to pick up skill updates.

---

## Two ways to use it in Claude Code

This repo ships with both a **skill** (slash command) and an **MCP plugin** (structured tools). Use whichever fits your workflow.

| | Skill (`/tailor-resume`) | MCP Plugin |
|---|---|---|
| How to activate | `/tailor-resume` slash command | Automatic on project open |
| How Claude uses it | Reads instructions, runs shell commands | Calls typed Python functions directly |
| Input | Paste text in chat | Structured JSON arguments |
| Best for | Interactive, conversational tailoring | Programmatic use, scripting, agents |

---

## Option A: Claude Code skill (slash command)

### Per-project (recommended — no copy needed)

If you cloned the repo, the skill is already at `.claude/skills/tailor-resume/`. Claude Code detects it automatically when you open the project folder.

Open the project in VS Code with the Claude Code extension, or run Claude Code from the repo root:

```bash
cd tailor-resume
claude
```

The skill appears in Claude's available skills list immediately.

### Global install (use from any project)

```bash
make install-global
```

This single command:
1. Registers the MCP server in `~/.claude/.mcp.json`
2. Copies the skill to `~/.claude/skills/tailor-resume/`
3. Installs optional deps (`pinecone`, `openai`) for RAG + semantic search

Restart Claude Code once. The skill and MCP tools are then available in every project.

### Use the skill

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

## Option B: MCP plugin (structured tools)

The MCP plugin exposes the pipeline as four typed tools that Claude Code calls directly — no slash command needed. Claude invokes the right tool automatically based on what you describe.

### Install

```bash
pip install -r requirements-optional.txt   # adds mcp>=1.0
```

### Activate

The plugin is pre-configured in `.claude/.mcp.json`. Open the project in Claude Code and restart it. The four tools appear automatically:

```
tailor-resume: extract_profile
tailor-resume: analyze_gap
tailor-resume: render_latex
tailor-resume: run_pipeline
```

No slash command required. Just describe what you want in chat — Claude picks the right tool.

### The four tools

**`extract_profile(text, format)`**
Parse any resume text into a structured profile JSON.
- `text`: raw resume content
- `format`: `blob` | `markdown` | `latex` | `linkedin` (default: `blob`)
- Returns: JSON with `experience`, `projects`, `skills`, `education`, `certifications`

**`analyze_gap(jd_text, resume_text, top_n)`**
Score a resume against a job description.
- Returns: ATS score (0-100), top gap signals with priorities and closing angles, keyword gaps, recommendations

**`render_latex(profile_json, output_path, name, email, ...)`**
Render a `resume.tex` from a profile dict.
- PII (`name`, `email`, `phone`, `linkedin`, `github`, `portfolio`) injected at runtime
- Returns: absolute path to the written `.tex` file

**`run_pipeline(jd_text, artifact_text, artifact_format, output_path, name, email, ...)`**
Full pipeline in one call: parse → gap analysis → render.
- Returns: profile dict, gap report, output path

### Example: full pipeline in one chat message

```
Here is my JD: [paste JD]
Here is my work history: [paste blob]
My name is Jane Smith, email jane@example.com, LinkedIn https://linkedin.com/in/jane
Write the resume to out/resume.tex
```

Claude calls `run_pipeline(...)` and returns the gap report + confirms the .tex path.

### Connect globally (use from any project)

To use the MCP plugin outside this repo, add it to your global Claude Code config:

**`~/.claude/.mcp.json`:**
```json
{
  "mcpServers": {
    "tailor-resume": {
      "command": "python",
      "args": ["/absolute/path/to/tailor-resume/.claude/skills/tailor-resume/scripts/mcp_server.py"]
    }
  }
}
```

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

The scripts under `.claude/skills/tailor-resume/scripts/` are standalone Python — core pipeline uses stdlib only.

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

**Full pipeline in one command (cli.py):**
```bash
mkdir -p out
python .claude/skills/tailor-resume/scripts/cli.py \
  --jd fixtures/sample_jd.txt \
  --artifact fixtures/sample_blob.txt:blob \
  --name "Jane Smith" --email "jane@example.com" \
  --linkedin "https://linkedin.com/in/jane-smith" \
  --output out/resume.tex
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
├── .claude/
│   ├── .mcp.json                 — MCP plugin config (auto-loaded by Claude Code)
│   └── skills/tailor-resume/
│       ├── SKILL.md              — skill instructions and 8-step workflow
│       ├── REFERENCE.md          — 2026 resume philosophy, bullet scoring rubric
│       ├── EXAMPLES.md           — invocation examples and blob format templates
│       ├── scripts/
│       │   ├── resume_types.py        — shared dataclasses (Bullet/Role/Profile/GapReport)
│       │   ├── text_utils.py          — shared utilities (extract_metrics, tokenize, ...)
│       │   ├── profile_extractor.py   — parse blobs, LaTeX, markdown, LinkedIn PDF
│       │   ├── jd_gap_analyzer.py     — JD gap analysis, ATS score, signal taxonomy
│       │   ├── latex_renderer.py      — profile dict → LaTeX resume
│       │   ├── rag_store.py           — Pinecone/SQLite profile persistence
│       │   ├── cli.py                 — single-command pipeline orchestrator
│       │   └── mcp_server.py          — MCP plugin server (4 tools for Claude Code)
│       └── templates/
│           └── resume_template.tex    — PII-free single-page LaTeX template
├── fixtures/
│   ├── sample_jd.txt              — sample Senior Data Engineer JD
│   ├── sample_blob.txt            — sample work experience blob
│   └── sample_profile.json        — pre-parsed profile for fast tests
├── tests/
│   ├── conftest.py                — shared fixtures and sys.path setup
│   ├── test_tracer_e2e.py         — end-to-end pipeline tests
│   ├── test_profile_extractor.py  — parser unit tests
│   ├── test_jd_gap_analyzer.py    — gap analysis unit tests
│   ├── test_latex_renderer.py     — renderer unit tests
│   ├── test_rag_store.py          — SQLite backend tests
│   └── test_cli.py                — CLI entry point tests
├── Makefile                       — setup/demo/test/lint/render/clean targets
├── requirements.txt               — pytest, ruff (core scripts use stdlib only)
├── requirements-optional.txt      — pinecone-client, openai, mcp
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
