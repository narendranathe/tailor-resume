"""
cli.py
Thin CLI shell for the tailor-resume pipeline.

All pipeline logic lives in pipeline.py.  This file contains only:
  - argparse wiring
  - file-path → TailorConfig conversion
  - stdout printing of the gap report

Usage:
    python cli.py \\
        --jd fixtures/sample_jd.txt \\
        --artifact fixtures/sample_blob.txt:blob \\
        --name "Jane Smith" \\
        --email "jane@example.com" \\
        --output out/resume.tex

    # Multiple artifacts (merged):
    python cli.py \\
        --jd jd.txt \\
        --artifact resume.md:markdown \\
        --artifact linkedin.txt:linkedin \\
        --name "Jane" --email "jane@example.com" \\
        --output out/resume.tex

    # GitHub profile as artifact source:
    python cli.py \\
        --jd jd.txt \\
        --artifact github:myusername \\
        --name "Jane" --email "jane@example.com" \\
        --output out/resume.tex

Artifact format: <path>:<format>
    Formats: blob | markdown | latex | linkedin | github
    Default format if omitted: blob

    Special form for GitHub: github:<username>
      The "path" portion is treated as a GitHub username.
      Requires GITHUB_TOKEN env var for private repos and higher rate limits.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add scripts dir to path when run standalone
_SCRIPTS = Path(__file__).parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from pipeline import TailorConfig, execute  # noqa: E402
from profile_extractor import (  # noqa: E402
    merge_profiles,
    parse_blob,
    parse_latex,
    parse_linkedin,
    parse_markdown,
)
from resume_types import Profile, profile_to_dict  # noqa: E402

_VALID_FORMATS = {"blob", "markdown", "latex", "linkedin", "github"}

_FILE_PARSERS = {
    "blob": parse_blob,
    "markdown": parse_markdown,
    "latex": parse_latex,
    "linkedin": parse_linkedin,
}

_DEFAULT_TEMPLATE = str(
    Path(__file__).parent.parent / "templates" / "resume_template.tex"
)


def run_pipeline(
    jd_path: str,
    artifacts: list,
    output_path: str,
    header: dict,
    template_path: str = _DEFAULT_TEMPLATE,
    top_gaps: int = 5,
) -> None:
    """Backward-compat wrapper — delegates to pipeline.execute()."""
    with open(jd_path, encoding="utf-8") as f:
        jd_text = f.read()
    config = TailorConfig(
        jd_text=jd_text,
        artifacts=artifacts,
        output_path=output_path,
        header=header,
        template_path=template_path,
        top_gaps=top_gaps,
    )
    result = execute(config)
    print("\n=== Gap Analysis ===")
    for line in result.gap_summary:
        print(line)
    print(f"\n[OK] Resume written to: {result.output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="tailor-resume pipeline: artifact(s) + JD -> LaTeX resume",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--jd", required=True, help="Path to job description text file")
    parser.add_argument(
        "--artifact",
        action="append",
        dest="artifacts",
        metavar="PATH:FORMAT",
        required=True,
        help="Resume artifact as path:format (format: blob|markdown|latex|linkedin). Repeatable.",
    )
    parser.add_argument(
        "--template",
        default=_DEFAULT_TEMPLATE,
        help="Path to LaTeX template (default: built-in resume_template.tex)",
    )
    parser.add_argument("--output", default="out/resume.tex", help="Output .tex path")
    parser.add_argument("--name", default="", help="Full name")
    parser.add_argument("--phone", default="", help="Phone number")
    parser.add_argument("--email", default="", help="Email address")
    parser.add_argument("--linkedin", default="", help="LinkedIn URL")
    parser.add_argument("--github", default="", help="GitHub URL")
    parser.add_argument("--portfolio", default="", help="Portfolio URL")
    parser.add_argument("--top-gaps", type=int, default=5, help="Number of gap signals to show")
    args = parser.parse_args()

    # Validate and parse artifact strings.
    # Standard form: <file_path>:<format>  e.g. resume.md:markdown
    # GitHub form:   github:<username>     e.g. github:octocat
    #   In the GitHub form the conventional order is reversed: the prefix "github"
    #   identifies the format and the remainder is the username (the "path").
    artifacts = []
    for raw in args.artifacts:
        if raw.startswith("github:"):
            # Special case: github:<username>
            username_part = raw[len("github:"):]
            path, fmt = username_part, "github"
        elif ":" in raw:
            path, fmt = raw.rsplit(":", 1)
        else:
            path, fmt = raw, "blob"
        if fmt not in _VALID_FORMATS:
            parser.error(f"Unknown format '{fmt}'. Choose from: {sorted(_VALID_FORMATS)}")
        artifacts.append((path, fmt))

    with open(args.jd, encoding="utf-8") as f:
        jd_text = f.read()

    # Separate GitHub artifacts from file-based artifacts.
    github_artifacts = [(path, fmt) for path, fmt in artifacts if fmt == "github"]
    file_artifacts = [(path, fmt) for path, fmt in artifacts if fmt != "github"]

    header = {
        "name": args.name,
        "phone": args.phone,
        "email": args.email,
        "linkedin": args.linkedin,
        "github": args.github,
        "portfolio": args.portfolio,
    }

    if not github_artifacts:
        # No GitHub artifacts: delegate entirely to pipeline.execute() as before.
        config = TailorConfig(
            jd_text=jd_text,
            artifacts=file_artifacts,
            output_path=args.output,
            header=header,
            template_path=args.template,
            top_gaps=args.top_gaps,
        )
        result = execute(config)
    else:
        # One or more GitHub artifacts: build GitHub profiles then merge with
        # any file-based artifacts and run the pipeline steps manually.
        import json  # noqa: PLC0415 — local import fine here
        from jd_gap_analyzer import run_analysis  # noqa: PLC0415
        from latex_renderer import build_from_profile  # noqa: PLC0415
        from pathlib import Path as _Path  # noqa: PLC0415

        # 1. Parse GitHub profiles.
        github_profiles: list = []
        try:
            from github_ingester import inject_github_projects  # noqa: PLC0415
        except ImportError:
            print(
                "[tailor-resume] github_ingester is not available. "
                "Install dependencies with: pip install requests PyGithub"
            )
            sys.exit(1)

        for username, _fmt in github_artifacts:
            empty_profile: dict = {
                "experience": [], "projects": [], "skills": [],
                "education": [], "certifications": [], "summary": "", "contact": {},
            }
            try:
                gh_profile_dict = inject_github_projects(empty_profile, username)
            except Exception as exc:  # noqa: BLE001
                print(f"[tailor-resume] GitHub ingestion failed for '{username}': {exc}")
                gh_profile_dict = empty_profile
            # Convert plain dict to Profile dataclass so merge_profiles can accept it.
            from resume_types import Project, Bullet  # noqa: PLC0415
            github_profiles.append(
                Profile(
                    projects=[
                        Project(
                            name=p.get("name", ""),
                            tech=p.get("tools", []),
                            bullets=[
                                Bullet(
                                    text=b.get("text", ""),
                                    metrics=b.get("metrics", []),
                                    tools=b.get("tools", []),
                                    evidence_source=b.get("evidence_source", "github"),
                                    confidence=b.get("confidence", "medium"),
                                )
                                for b in p.get("bullets", [])
                            ],
                        )
                        for p in gh_profile_dict.get("projects", [])
                    ],
                )
            )

        # 2. Parse file-based artifacts.
        file_profiles: list = []
        for path, fmt in file_artifacts:
            file_parser = _FILE_PARSERS[fmt]
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            file_profiles.append(file_parser(text))

        # 3. Merge all profiles.
        all_profiles = file_profiles + github_profiles
        if len(all_profiles) > 1:
            merged = merge_profiles(*all_profiles)
        elif all_profiles:
            merged = all_profiles[0]
        else:
            merged = Profile()
        profile_dict = profile_to_dict(merged)

        # 4. Gap analysis.
        report = run_analysis(jd_text, json.dumps(profile_dict), top_n=args.top_gaps)

        # 5. Render LaTeX.
        _Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        build_from_profile(profile_dict, args.template, args.output, header)

        # 6. Build a result-like namespace so the print block below is uniform.
        gap_lines: list = [f"ATS Score: {report.ats_score_estimate}/100"]
        for i, gap in enumerate(report.top_missing, 1):
            gap_lines.append(f"{i}. [{gap.priority.upper()}] {gap.category}")
            gap_lines.append(f"   Missing: {', '.join(gap.jd_keywords[:5])}")
            for angle in gap.suggested_angles:
                gap_lines.append(f"     - {angle}")
        for rec in report.recommendations:
            gap_lines.append(f"  * {rec}")

        class _Result:  # noqa: N801
            gap_summary = gap_lines
            output_path = args.output

        result = _Result()

    print("\n=== Gap Analysis ===")
    for line in result.gap_summary:
        print(line)
    print(f"\n[OK] Resume written to: {result.output_path}")


if __name__ == "__main__":
    main()
