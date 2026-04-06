# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the pipeline

**CLI (file-based artifacts):**
```bash
python scripts/cli.py \
  --jd fixtures/sample_jd.txt \
  --artifact fixtures/sample_blob.txt:blob \
  --name "Jane Smith" --email "jane@example.com" \
  --output out/resume.tex

# With PDF compile + cover letter:
python scripts/cli.py --jd jd.txt --artifact resume.md:markdown \
  --name "Jane" --email "jane@example.com" \
  --output out/resume.tex --pdf --cover-letter
```

Artifact formats: `blob` | `markdown` | `latex` | `linkedin`

**MCP server (for Claude Code integration):**
```bash
python scripts/mcp_server.py
```

Configure in `.claude/.mcp.json`:
```json
{
  "mcpServers": {
    "tailor-resume": {
      "command": "python",
      "args": [".claude/skills/tailor-resume/scripts/mcp_server.py"]
    }
  }
}
```

**PDF export:**
```bash
pdflatex resume.tex
# If references: run twice
```
Or upload to Overleaf with pdfLaTeX compiler.

## Architecture

The pipeline is split into a pure-data layer and a side-effect boundary:

```
TailorConfig (data in)
      ↓
pipeline.execute() ← side-effect boundary (file reads, gap analysis, LaTeX write)
      ↓
TailorResult (data out)
```

- **`pipeline.py`** — single source of truth for pipeline orchestration; `execute()` (file-based) and `execute_text()` (in-memory, used by MCP). Both `cli.py` and `mcp_server.py` delegate to this.
- **`profile_extractor.py`** — parses artifacts into a canonical `Profile` dataclass. `merge_profiles()` combines multiple inputs. Parsers: `parse_blob`, `parse_markdown`, `parse_latex`, `parse_linkedin`.
- **`jd_gap_analyzer.py`** — `run_analysis(jd_text, resume_text, top_n)` → `GapReport` with `ats_score_estimate`, `top_missing`, `keyword_gaps`, `recommendations`.
- **`latex_renderer.py`** — `build_from_profile(profile_dict, template_path, output_path, header)` → writes `resume.tex`. Header PII is injected at runtime only.
- **`cover_letter_renderer.py`** — `build_cover_letter(profile_dict, report, header, jd_text)` → LaTeX string. Lazy-imported only when `cover_letter=True`.
- **`resume_types.py`** — shared dataclasses: `Profile`, `GapReport`, `GapSignal`, `Bullet`. `profile_to_dict()` converts `Profile` to plain dict for JSON serialization.
- **`mcp_server.py`** — exposes 5 MCP tools: `extract_profile`, `analyze_gap`, `render_latex`, `run_pipeline`, `generate_cover_letter`. All return JSON strings.

### parsers/ subpackage
Format-specific extraction logic: `pdf_extractor.py`, `docx_extractor.py`, `markdown_parser.py`, `plain_parser.py`, `latex_parser.py`, `normalizer.py`.

### stores/ subpackage
RAG persistence for reuse across sessions. `factory.get_store()` returns `PineconeStore` if `PINECONE_API_KEY` is set, else `SQLiteStore`. Both implement `stores/base.py` interface.

## Key invariants
- **No PII in templates** — `templates/resume_template.tex` has no hardcoded names/emails. All contact info flows through the `header` dict at render time.
- **Single-page output always** — enforced by the iterative loop in `SKILL.md` (max 3 passes).
- **No fabrication** — gap angles are suggested prompts, not invented claims. The pipeline never writes content the user didn't confirm.
- **STAR + 2-line rule** — every bullet output must pass `star_validator.score_star()`: Action + Result (STAR score ≥2/2) and word count ≤20. `latex_renderer.truncate_to_limit()` enforces the word limit automatically at render; write compliant bullets before reaching the renderer.
- **ATS formula (4-component)** — `40% keyword overlap + 30% category coverage + 20% bullet quality (STAR+metrics) + 10% seniority signal`. Implemented in `jd_gap_analyzer.estimate_ats_score()`.
- **Multi-tenancy** — `user_id: str = ""` flows through `TailorConfig`, `TailorResult`, `GapReport`, and `mcp_server.run_pipeline`. Empty = anonymous (single-user default). RAG store methods accept `user_id` at each call site; SQLite index is on `(user_id, stored_at DESC)`.
- **All scripts add their own directory to `sys.path`** — allows running from any CWD without `PYTHONPATH` setup.
