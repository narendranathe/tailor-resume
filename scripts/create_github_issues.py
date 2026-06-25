"""
create_github_issues.py
Creates GitHub issues for both PRDs (ATS 99+ and Parsing enhancements).

Usage:
    pip install PyGithub
    GITHUB_TOKEN=<your-token> python scripts/create_github_issues.py

Or with gh CLI (if installed):
    gh auth status   # must be logged in
    python scripts/create_github_issues.py --use-gh
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from typing import List

REPO = "narendranathe/tailor-resume"

@dataclass
class Issue:
    title: str
    body: str
    labels: List[str]


ISSUES: List[Issue] = [
    # -----------------------------------------------------------------------
    # PRD tracking issues
    # -----------------------------------------------------------------------
    Issue(
        title="PRD: 99+ ATS Score Pipeline Improvements (prd_ats_99.md)",
        body="""\
## Summary
Product Requirements Document for 14 improvements to the ATS scoring pipeline.
All 14 fixes have been implemented in commit `ee2b528`.

See full spec: `specs/prd_ats_99.md`

## Implemented fixes
| # | Fix | File | Status |
|---|-----|------|--------|
| 1 | `round()` not `int()` in `estimate_ats_score` | jd_gap_analyzer.py | ✅ |
| 2 | Token filter `>= 2` chars, catches ml/ai/go/ci | text_utils.py | ✅ |
| 3 | SUMMARY_SECTION active in template | resume_template.tex | ✅ |
| 4 | Plain-text bullet fallback in scoring | jd_gap_analyzer.py | ✅ |
| 5 | ACTION_VERBS +26 senior-IC verbs | star_validator.py | ✅ |
| 6 | `_has_action` searches all words, not first 6 | star_validator.py | ✅ |
| 7 | TOOL_VOCAB 43 → 85 tools | resume_types.py | ✅ |
| 8 | `_SENIORITY_WORDS` 7 → 14 words | jd_gap_analyzer.py | ✅ |
| 9 | Recommendations for all 10 taxonomy categories | jd_gap_analyzer.py | ✅ |
| 10 | Word-boundary matching in category coverage | jd_gap_analyzer.py | ✅ |
| 11 | `min_freq=1` in `keyword_gaps` | jd_gap_analyzer.py | ✅ |
| 12 | New metric patterns: sub-ms, headcount, NPS, ranked | text_utils.py | ✅ |
| 13 | GITHUB_URL/DISPLAY placeholders in template | resume_template.tex | ✅ |
| 14 | Word-count penalty in `bullet_quality_score` | star_validator.py | ✅ |
""",
        labels=["prd", "enhancement", "ats-score"],
    ),
    Issue(
        title="PRD: PDF Parsing Accuracy Enhancements (prd_pdf_parsing.md)",
        body="""\
## Summary
Product Requirements Document for PDF parsing accuracy improvements.
All fixes implemented.

See full spec: `specs/prd_pdf_parsing.md`

## Implemented
- Fix 1: Column-gap detection scans all x0 pairs (removed early break)
- Fix 2: Left column emitted before right (reading order)
- Fix 3: `_box_lines` returns raw lines only, no spurious bullet injection
- Fix 4: `LAParams(boxes_flow=None, line_margin=0.5)` prevents column bleed
- Fix 5: `_DATE_PATTERN` includes `to|thru|through` separators + MM/YYYY + ISO
- Fix 6: `_SECTION_HEADERS` extended with employment history, side projects, achievements, summary/profile/objective
""",
        labels=["prd", "parsing"],
    ),

    # -----------------------------------------------------------------------
    # Individual enhancement issues (for backlog tracking)
    # -----------------------------------------------------------------------
    Issue(
        title="enhancement: contact info (name/email/phone/linkedin/github) parsed from resume preamble",
        body="""\
## Problem
The candidate's name, email, phone, and LinkedIn/GitHub URLs appearing before the
first section header were silently discarded. The renderer required these values
to be passed manually in the `header` dict, creating a disconnect between what
the parser saw and what the renderer used.

## Solution
`plain_parser.py` now scans preamble lines with `_EMAIL_RE`, `_PHONE_RE`, and
`_URL_RE` regexes, populating `Profile.contact` dict (`name`, `email`, `phone`,
`linkedin`, `github`). The renderer can read these values instead of requiring
manual header injection.

## Files changed
- `parsers/plain_parser.py`: preamble handler, `_EMAIL_RE`, `_PHONE_RE`, `_URL_RE`
- `resume_types.py`: `Profile.contact: Dict = field(default_factory=dict)`

Implemented in commit `ee2b528`.
""",
        labels=["enhancement", "parsing"],
    ),
    Issue(
        title="enhancement: Summary/Profile/Objective section captured into Profile.summary",
        body="""\
## Problem
Resumes with a Summary, Profile, or Objective section had that content silently
dropped — or misidentified as a role if the section header wasn't recognized.

## Solution
Added `"summary"` canonical section to `_SECTION_HEADERS` with aliases:
`summary`, `profile`, `objective`, `professional summary`, `summary of qualifications`, `about me`.
Content is accumulated into `Profile.summary: str = ""`.

The LaTeX renderer now replaces `{{SUMMARY_SECTION}}` with a full
`\\section{Summary}` block when non-empty, or an empty string when absent.

Implemented in commit `ee2b528`.
""",
        labels=["enhancement", "parsing"],
    ),
    Issue(
        title="enhancement: Responsibilities: / Key Achievements: subheader lines no longer restart a ghost role",
        body="""\
## Problem
Within experience roles, lines like `Responsibilities:` or `Key Achievements:`
matched `_like_title_line()` and triggered a ghost role entry with no company/date.

## Solution
In the experience section parser: if `current_role` is already set and the current
line ends with `:` and has ≤5 words, treat it as a subheader label and skip it.

Implemented in commit `ee2b528`.
""",
        labels=["bug", "parsing"],
    ),
    Issue(
        title="enhancement: bullet wrap-continuation for experience section (lowercase line → appended to last bullet)",
        body="""\
## Problem
Long experience bullets wrapping across PDF lines appeared as two separate lines
in extracted text. The second line sometimes matched `_like_title_line()` heuristics
and started a ghost role, or was silently dropped.

## Solution
Added an `elif` branch after the bullet detector in the experience section:
if the line starts lowercase, has no date, and `current_role.bullets` is non-empty,
append the line to the last bullet's text and re-extract metrics/tools.

Mirrors the existing wrap-continuation logic already present in the projects section.

Implemented in commit `ee2b528`.
""",
        labels=["bug", "parsing"],
    ),
    Issue(
        title="enhancement: _split_bullet_block no longer over-splits technical 2-sentence bullets",
        body="""\
## Problem
`_split_bullet_block` split paragraphs at every `period + uppercase` boundary,
fragmenting technically correct single bullets like:
`Reduced latency by 40%. Deployed via Kubernetes.`
into two phantom bullets with broken context.

## Solution
The function now only splits a paragraph into sub-sentences when it contains
**3+ sentences** (≥2 `. ` occurrences). Two-sentence technical bullets stay intact.

Implemented in commit `ee2b528`.
""",
        labels=["bug", "parsing"],
    ),
    Issue(
        title="enhancement: parse_pdf(debug=True) returns raw extracted text with tier label",
        body="""\
## Problem
When parsing failed silently (empty roles, missing bullets), there was no visibility
into which extraction tier fired and what raw text it produced.

## Solution
`parse_pdf(file_bytes, debug=True)` now returns `(Profile, str)` where the string
is `# tier: pdfminer|pypdf|stdlib\\n\\n<raw text>`. Normal calls without `debug`
still return `Profile`.

Usage:
```python
profile, raw = parse_pdf(pdf_bytes, debug=True)
print(raw)  # inspect what the regex state machine saw
```

Implemented in commit `ee2b528`.
""",
        labels=["enhancement", "parsing"],
    ),
    Issue(
        title="future: education — parse GPA, degree, institution from a single condensed line",
        body="""\
## Problem
Many resumes condense education to a single line:
```
Missouri S&T — M.S. Information Science | GPA: 4.0 | Jan 2022 – Dec 2023
```
The current multi-line education parser misses this format, producing empty fields.

## Proposed solution
Add a composite regex that tries to extract institution, degree, GPA, and dates
from a single line before falling back to the multi-line heuristic:
```python
_EDU_ONELINER_RE = re.compile(
    r"(?P<inst>[A-Z][^|–\-]+?)\s*[|–\-]\s*"
    r"(?P<deg>[^|]+?)\s*[|–\-]?\s*"
    r"(?:GPA[:\s]+(?P<gpa>[\d.]+))?"
)
```

Not yet implemented. Tracked for future sprint.
""",
        labels=["enhancement", "parsing", "future"],
    ),
]


def create_via_api(token: str) -> None:
    try:
        from github import Auth, Github
    except ImportError:
        print("PyGithub not installed. Run: pip install PyGithub")
        sys.exit(1)

    g = Github(auth=Auth.Token(token))
    repo = g.get_repo(REPO)

    # Create labels if they don't exist (colors without # prefix)
    existing_labels = {lb.name for lb in repo.get_labels()}
    label_defs = {
        "prd": ("0075ca", "Product Requirements Document"),
        "ats-score": ("e4e669", "ATS scoring pipeline improvements"),
        "parsing": ("d93f0b", "PDF / plain-text parsing"),
        "enhancement": ("a2eeef", "New feature or request"),
        "bug": ("d73a4a", "Something is broken"),
        "future": ("cfd3d7", "Planned for a future sprint"),
    }
    for name, (color, desc) in label_defs.items():
        if name not in existing_labels:
            repo.create_label(name, color, desc)
            print(f"  Created label: {name}")
        else:
            print(f"  Label exists: {name}")

    existing_titles = {i.title for i in repo.get_issues(state="open")}
    for issue in ISSUES:
        if issue.title in existing_titles:
            safe = issue.title.encode("ascii", "replace").decode()
            print(f"  SKIP (exists): {safe}")
            continue
        created = repo.create_issue(
            title=issue.title,
            body=issue.body,
            labels=issue.labels,
        )
        safe_title = issue.title.encode("ascii", "replace").decode()
        print(f"  #{created.number}: {safe_title}")


def create_via_gh() -> None:
    for issue in ISSUES:
        label_str = ",".join(issue.labels)
        cmd = ["gh", "issue", "create",
               "--title", issue.title,
               "--body", issue.body,
               "--label", label_str]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"  Created: {result.stdout.strip()}")
        else:
            print(f"  Error: {result.stderr.strip()}")


if __name__ == "__main__":
    use_gh = "--use-gh" in sys.argv
    if use_gh:
        print("Creating issues via gh CLI...")
        create_via_gh()
    else:
        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            print("Set GITHUB_TOKEN env var or pass --use-gh flag.")
            print("\nIssues to create:")
            for i, issue in enumerate(ISSUES, 1):
                print(f"  {i}. {issue.title}")
            sys.exit(0)
        print("Creating issues via GitHub API...")
        create_via_api(token)
