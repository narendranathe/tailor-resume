# PRD: Template & Renderer Sprint

## Problem

The resume pipeline has three defects that degrade output quality and ATS pass-through. First, the Summary section placeholder `{{SUMMARY_SECTION}}` exists in `resume_template.tex` but must be verified as uncommented and live so that populated summaries appear in the PDF — a blank summary silently lowers ATS scores on roles that weight professional summaries. Second, `latex_renderer.py` has no DOCX export path, forcing users to compile LaTeX locally or via Overleaf before they can attach a resume to an application; DOCX is required by ~60% of ATS portals that reject PDF. Third, URL fields (`EMAIL`, `LINKEDIN_URL`, `GITHUB_URL`, `PORTFOLIO_URL`) are passed raw into the LaTeX template without `escape()`, meaning any `%` or `#` in those strings (common in tracking URLs and mailto strings) silently breaks compilation with a cryptic LaTeX error. Without these fixes, users receive broken PDFs or no output at all on real-world profiles.

## Users

| Persona | Resume source / entry point | Impact |
|---|---|---|
| Active job seeker | LinkedIn blob + JD paste via Claude skill | Broken PDF on profiles with LinkedIn tracking URLs; missing summary section |
| Career changer | Manual JSON profile via CLI | DOCX unavailable; must install pdflatex locally |
| Recruiter / HR (receives output) | ATS portal upload | PDF rejected by portals requiring .docx; summary omission lowers match score |

## User Stories

1. As a job seeker, I want my professional summary to appear in the rendered PDF so that recruiters see my positioning statement without me manually editing the .tex file.
2. As a job seeker with no LaTeX toolchain, I want to run `python latex_renderer.py --docx` and receive a formatted `.docx` file so that I can attach it directly to ATS portals without installing pdflatex.
3. As a pipeline developer, I want URL fields to be safely escaped before LaTeX injection so that profiles containing `%`-encoded or `#`-fragment URLs compile without errors.

## Flow

```
BEFORE
------
profile dict
    |
    v
build_from_profile()
    |-- SUMMARY_SECTION: rendered but risk of being commented in template
    |-- EMAIL / LINKEDIN_URL: raw string → LaTeX crash on % or #
    |
    v
render_template() → resume.tex  ←→  pdflatex (user must have toolchain)
                                      NO .docx path


AFTER
-----
profile dict
    |
    v
build_from_profile()
    |-- SUMMARY_SECTION: confirmed live in template (not commented)
    |-- EMAIL display text: escape()  (href URL arg left raw — hyperref handles it)
    |-- LINKEDIN_DISPLAY / GITHUB_DISPLAY / PORTFOLIO_DISPLAY: escape()
    |
    +--------> render_template() → resume.tex  →  pdflatex (unchanged)
    |
    +--------> build_docx_from_profile() → resume.docx  (NEW, no LaTeX needed)
```

## Modules

| File | Line range | Exact change description |
|---|---|---|
| `templates/resume_template.tex` | 100–101 | Verify `{{SUMMARY_SECTION}}` is uncommented and live; no action needed if already active |
| `scripts/latex_renderer.py` | 231–240 | Wrap `LINKEDIN_DISPLAY`, `GITHUB_DISPLAY`, `PORTFOLIO_DISPLAY` display values with `escape()` |
| `scripts/latex_renderer.py` | 258–296 (new) | Add `build_docx_from_profile()` function using python-docx |
| `scripts/latex_renderer.py` | 263–292 (CLI) | Add `--docx` flag to argparse `main()` and wire to `build_docx_from_profile()` |

## Acceptance Criteria

- [x] The rendered `.tex` output contains a `\section{Summary}` block when a non-empty summary is present in the profile dict.
- [x] The rendered `.tex` output contains NO `\section{Summary}` block when summary is absent or empty string.
- [x] `build_docx_from_profile()` produces a valid `.docx` file (openable by python-docx) containing name, experience, education, and skills sections without raising an exception.
- [x] A profile header with `email` containing `%` or `#` does not raise a LaTeX compilation error (display text is escaped; href URL arg is left unescaped for hyperref).
- [x] Running `python latex_renderer.py --profile p.json --docx --output resume.docx` writes a `.docx` to the specified path.
- [x] All existing `test_latex_renderer.py` tests continue to pass after changes.

## Metrics

| Metric | Before | After |
|---|---|---|
| test_latex_renderer.py passing tests | Baseline (all) | All + new DOCX test |
| Summary section present when summary provided | Unverified | Confirmed: `\section{Summary}` in output |
| DOCX output available | 0 code paths | 1 (`build_docx_from_profile`) |
| URL escape coverage (display text fields) | 0 of 4 escaped | 3 of 3 display fields escaped (EMAIL display text also escaped) |
| LaTeX crash rate on URLs with `%` or `#` | > 0 (unmitigated) | 0 (display text escaped) |
