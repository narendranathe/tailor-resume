# PRD: Wire github_ingester.py into CLI and MCP Server

## Problem

`github_ingester.py` ships a complete implementation — `fetch_user_repos()`, `ingest_repo()`, and `inject_github_projects()` — but neither `cli.py` nor `mcp_server.py` exposes any entry point for it. A user who wants to pull their GitHub projects into a tailored resume must manually write a Python script to call these functions, serialize the output, and somehow pipe it into the pipeline. This friction defeats the purpose of the ingester, and leaves its 480-line implementation effectively dead code with zero test coverage through any user-facing path. Without wiring, every GitHub-first candidate (engineers who keep a richer GitHub profile than a traditional resume) is forced to either craft a blob artifact by hand or skip their project evidence entirely, reducing ATS scores by an estimated 15–20 points on project-heavy JDs.

## Users

| Persona | Resume source / entry point | Impact |
|---|---|---|
| GitHub-first engineer | Public GitHub profile as primary resume source | Cannot use existing projects in ATS-optimized resume without manual extraction |
| Recruiter / Claude Code user | Calls MCP tools to run full pipeline on behalf of a candidate | No `ingest_github` tool exists; must work around with raw blob paste |
| CLI power user | Runs `cli.py` with `--artifact` flags in shell scripts | No `github:username` format supported; must pre-process GitHub data separately |

## User Stories

- As a GitHub-first engineer, I want to run `cli.py --artifact github:myusername` so that my public repos are automatically extracted and included in my tailored resume without manual copy-paste.
- As a Claude Code user, I want to call the `ingest_github` MCP tool with a GitHub username so that I can programmatically enrich a candidate profile with their project history before running the full pipeline.
- As a CLI power user, I want the `github:username` artifact format to compose naturally with other `--artifact` flags so that I can merge GitHub projects with an existing LinkedIn or blob artifact in a single command.

## Flow

```
BEFORE
  User                    cli.py                  pipeline
  ──────────────────────────────────────────────────────
  --artifact file.txt:blob ──► parse blob  ──► profile (no github projects)
  [GitHub projects missing from output]

  Claude Code             mcp_server.py
  ──────────────────────────────────────
  [no ingest_github tool] → user must paste blob manually

AFTER
  User                    cli.py                  github_ingester          pipeline
  ───────────────────────────────────────────────────────────────────────────────
  --artifact github:user ──► detect "github" fmt ──► fetch_user_repos()
                                                  ──► inject_github_projects()
                                                  ──► profile dict ──────────────► merged profile
  (optional --artifact file.txt:blob also)   ──► parse blob ───────────────────►  ↑ merge_profiles

  Claude Code             mcp_server.py           github_ingester
  ───────────────────────────────────────────────────────────────
  ingest_github(username) ──► fetch_user_repos()
                          ──► inject_github_projects()
                          ──► JSON profile string returned to Claude Code
```

## Modules

| File | Line range | Exact change description |
|---|---|---|
| `cli.py` | Line 43 | Add `"github"` to `_VALID_FORMATS` set |
| `cli.py` | Lines 107–114 | In the artifact validation loop, allow `"github"` format to bypass file-existence check |
| `cli.py` | Lines 59–73 (run_pipeline) | Add GitHub profile building before `TailorConfig` construction; pass pre-built profile list |
| `cli.py` | Lines 119–140 (main) | After artifact parse loop, detect `github` format entries and build `github_profile_dict` via `inject_github_projects`; fold into artifacts list as pre-parsed profile |
| `mcp_server.py` | After line 271 (after `run_pipeline` tool) | Add new `@mcp.tool()` function `ingest_github(username)` that calls `fetch_user_repos` + `inject_github_projects` and returns profile JSON |
| `mcp_server.py` | Line 26 docstring | Update module docstring to list 5 tools instead of 4 |

## Acceptance Criteria

- [x] `python cli.py --jd fixtures/sample_jd.txt --artifact github:octocat --name "Jane" --email "j@x.com" --output /tmp/test.tex` runs without Python `KeyError` or `ValueError` on the format check; it either produces output or prints a clear network error if the API is unreachable.
- [x] When `github_ingester` cannot be imported (e.g., if the module is temporarily renamed), `cli.py` prints a user-friendly message (`github_ingester not available`) and exits cleanly rather than raising an unhandled `ImportError`.
- [x] The `ingest_github` function is registered as an MCP tool in `mcp_server.py` — it appears when `mcp.list_tools()` is called (or equivalently, when the server introspects its tools at startup).
- [x] `ingest_github("nonexistent-user-xyzzy123")` returns a JSON string containing `"projects"` key (possibly empty list) rather than raising an exception. Verified: HTTP 404 produces `{"projects": [], ...}` gracefully.
- [x] Mixing `--artifact github:user` with `--artifact file.txt:blob` in a single `cli.py` invocation does not raise a type error — both artifacts are processed and their profiles are merged.
- [x] `ImportError` in `mcp_server.py`'s `ingest_github` (missing `requests`/`PyGithub`) returns `{"error": "github_ingester dependencies not installed..."}` instead of an unhandled exception.

## Metrics

| Metric | Before | After |
|---|---|---|
| CLI artifact formats supported | 4 (blob, markdown, latex, linkedin) | 5 (+ github) |
| MCP tools exposed | 4 | 5 |
| Lines of github_ingester reachable via any user-facing path | 0 | ~200 (fetch_user_repos + inject_github_projects paths) |
| Manual steps for GitHub-first candidate | 3+ (run ingester, serialize, pass to pipeline) | 1 (`--artifact github:username`) |
| Estimated ATS score ceiling for project-heavy JD | Capped (no project bullets) | Full (projects injected from GitHub) |
