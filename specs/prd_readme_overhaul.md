# PRD: README Overhaul — Complete Project Documentation

> Product-Driven Development pipeline: **Problem → Users → Stories → Flow → Modules → Acceptance → Metrics**

---

## Problem Statement

The existing README was a user-facing install guide with no institutional knowledge. It documented installation paths and Streamlit usage but contained none of the architectural decisions, development history, error forensics, ubiquitous language, or design rationale accumulated across 7 phases of development and 17+ PRDs. When a new session begins with Claude Code, or a new contributor opens the repo, they have no way to understand why decisions were made — only what exists now.

Three concrete gaps:

1. **Missing institutional memory** — 15 ATS scoring bugs, 9 design decisions, real production errors (OT1 corruption, silent Stripe drops, JWT auth exploits) are documented in `specs/` PRDs but not surfaced anywhere a contributor will look first.
2. **No developer onboarding** — no ubiquitous language reference, no file map with purpose descriptions, no explanation of the 4-tier PDF extraction chain or the storage fallback pattern.
3. **No feedback loop** — contributors had no documented path for submitting feedback on skill behavior, ATS scoring discrepancies, or bug reports with the right context.

---

## Users

| Persona | Need |
|---|---|
| New contributor | Understand architecture, file roles, design decisions, and conventions before writing code |
| Session-reopening Claude Code | Read PRDs, stages, and decisions to reconstruct context without relying on conversation memory |
| Job seeker (non-developer) | Understand what the tool does, how to use it, and how to export to PDF — in 2 minutes |
| Security reviewer | See auth, JWT, rate-limiting, and PII handling decisions in one place |

---

## User Stories

1. **As a new contributor**, I want to read the README and understand what every file does, what the canonical terms are, and why key architectural decisions were made — without reading all 17 PRDs.
2. **As a job seeker**, I want to understand in one paragraph what tailor-resume does and the three ways to use it, so I can pick the right path immediately.
3. **As a session-reopening Claude Code**, I want to read the Development Stages section and Errors & Fixes section and immediately understand the project's history without re-reading the full issue tracker.
4. **As a contributor with a bug**, I want to know exactly what to include in a GitHub issue and which label to use, so that feedback is actionable.

---

## Flow

### What was built

**README.md** — complete overhaul of `C:\Users\narendranath.edara\tailor-resume\README.md`:
- What it does (1 paragraph)
- How to use it (3 paths: Browser / Claude Code / CLI+API)
- Project Status tables (Tier 1–4) — existing content preserved
- Install instructions (pip / local clone / global Claude Code skill)
- For Developers section (contributing, PRD→Issue→PR process, feedback loop with labeled GitHub issues)
- Project structure (full annotated file tree)
- Architecture (data flow, ATS formula, PDF tiers, ATS Relevance Gate, storage fallback pattern, two runtimes)
- Ubiquitous language (canonical term table)
- Development stages (7-phase chronological timeline)
- Design decisions (9 decisions from PRDs with rationale)
- Errors encountered and how we fixed them (10 production errors with PRD citations)
- Key environment variables table
- Design principles

**Web artifact** — rendered HTML documentation page published at https://claude.ai/code/artifact/6a23ba4c-17d1-487b-a3cd-6ddf21163b86:
- Dark-mode design (ground `#0d1117`, surface `#161b22`, accent `#58a6ff`, muted `#8b949e`)
- System monospace headings (CLI tool — typographic choice is earned)
- Sticky left nav with scroll-spy active state
- 68ch readable content column
- `$` prefix on section headings as terminal prompt anchors (aesthetic risk)
- Status pills (green/yellow/blue) for feature tables
- ATS formula rendered as a structured formula block
- 4-tier PDF extraction table, timeline, decision cards, error items

---

## Modules Changed

| File | Change |
|---|---|
| `README.md` | Complete overhaul — from 547-line install guide to full project documentation |
| `specs/prd_readme_overhaul.md` | This PRD — documents the overhaul decision and scope |

---

## Acceptance Criteria

- [ ] README opens with a 1-paragraph description, not a table of contents
- [ ] Streamlit badge and CI badge are present at the top (links preserved from original)
- [ ] 3 usage paths are immediately visible (Browser / Claude Code / CLI)
- [ ] Project Status tables match the original tier structure
- [ ] Architecture section contains data flow, ATS formula breakdown, PDF tier table
- [ ] Ubiquitous language section lists all canonical terms with aliases to avoid
- [ ] Development stages covers all 7 phases with dates
- [ ] Design decisions covers all 9 choices with rationale
- [ ] Errors & fixes covers all 10 documented production errors with PRD citations
- [ ] Feedback section includes labeled GitHub issue guidance
- [ ] HTML artifact is published and accessible

---

## Metrics

- README: from 547 lines (install guide only) to ~450 lines of focused documentation
- Sections covered: 13 distinct documentation sections
- PRDs synthesized: 17
- GitHub issues analyzed: 46 open + closed
- Source files read: 18 (all pipeline scripts + web backend files)
- Web artifact sections: 11 (status, install, architecture, structure, language, env, stages, decisions, errors, contributing, feedback)
