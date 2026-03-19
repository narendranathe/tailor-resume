I open-sourced a resume tailoring tool built with Claude Code. Here's what it does and why I built it.

**The problem:** tailoring a resume to a job description is mechanical work. It's the same process every time: find the keywords, find the gaps, rewrite the bullets to fit. It shouldn't take two hours per application.

**What it does:**

Paste a JD and your work history. The tool runs gap analysis against 10 signal categories, tells you what's weak, rewrites your bullets to the "Accomplished X as measured by Y by doing Z" pattern with JD keywords integrated, and outputs a single-page LaTeX resume.

It doesn't fabricate. If a metric is missing it asks. It never guesses.

The output uses the Jake Gutierrez LaTeX template, the one that actually parses cleanly through ATS. You verify by selecting text in the exported PDF.

**What's useful about how it was built:**

The whole repo was built in one Claude Code session using a five-skill pipeline: PRD, vertical slice issues, architecture RFC with three sub-agents running in parallel evaluating different designs, TDD with tests written before any implementation, and a README rewrite.

The TDD pass caught a real bug. The architecture review found that four scripts were sharing data through untyped dicts instead of typed dataclasses. An RFC is open for the refactor.

The skills pipeline turned "build a resume tool" into a tracked project with 7 GitHub issues, 19 passing tests, and a documented architecture decision. That's the pattern I'll use for the next project.

**Repo:** github.com/narendranathe/tailor-resume

`git clone` + `pip install -r requirements.txt` + `pytest` = 19 green, no API keys.

6 open issues, Apache 2.0. Happy to answer questions about the gap analysis or the Claude Code skill setup.
