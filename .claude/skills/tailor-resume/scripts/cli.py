"""
cli.py
Thin orchestrator for the tailor-resume pipeline.

Chains: profile_extractor -> jd_gap_analyzer -> latex_renderer in a single command.
All resume logic lives in the individual modules; this file contains only glue.

Usage:
    python cli.py \\
        --jd fixtures/sample_jd.txt \\
        --artifact fixtures/sample_blob.txt:blob \\
        --name "Jane Smith" \\
        --email "jane@example.com" \\
        --linkedin "https://linkedin.com/in/jane-smith" \\
        --output out/resume.tex

    # Multiple artifacts (merged):
    python cli.py \\
        --jd jd.txt \\
        --artifact resume.md:markdown \\
        --artifact linkedin.txt:linkedin \\
        --name "Jane" --email "jane@example.com" \\
        --output out/resume.tex

Artifact format: <path>:<format>
    Formats: blob | markdown | latex | linkedin
    Default format if omitted: blob
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add scripts dir to path when run standalone  # noqa: E402
_SCRIPTS = Path(__file__).parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from jd_gap_analyzer import run_analysis  # noqa: E402
from latex_renderer import build_from_profile  # noqa: E402
from profile_extractor import (  # noqa: E402
    merge_profiles,
    parse_blob,
    parse_latex,
    parse_linkedin,
    parse_markdown,
)
from resume_types import profile_to_dict  # noqa: E402

_PARSERS = {
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
    artifacts: list[tuple[str, str]],
    output_path: str,
    header: dict,
    template_path: str = _DEFAULT_TEMPLATE,
    top_gaps: int = 5,
) -> None:
    """
    Full pipeline: parse artifacts -> gap analysis -> LaTeX output.

    Args:
        jd_path: Path to job description text file.
        artifacts: List of (file_path, format) tuples.
        output_path: Where to write resume.tex.
        header: Dict with name, email, phone, linkedin, github, portfolio.
        template_path: Path to LaTeX template.
        top_gaps: Number of top gap signals to print.
    """
    # 1. Parse all input artifacts and merge into one profile
    profiles = []
    for path, fmt in artifacts:
        parser = _PARSERS.get(fmt, parse_blob)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        profiles.append(parser(text))

    profile = merge_profiles(*profiles) if len(profiles) > 1 else profiles[0]
    profile_dict = profile_to_dict(profile)

    # 2. Gap analysis — prints report to stdout
    with open(jd_path, encoding="utf-8") as f:
        jd_text = f.read()

    resume_text = json.dumps(profile_dict)
    report = run_analysis(jd_text, resume_text, top_n=top_gaps)

    print("\n=== Gap Analysis ===")
    print(f"ATS Score: {report.ats_score_estimate}/100")
    for i, gap in enumerate(report.top_missing, 1):
        print(f"\n{i}. [{gap.priority.upper()}] {gap.category}")
        print(f"   Missing: {', '.join(gap.jd_keywords[:5])}")
        for angle in gap.suggested_angles:
            print(f"     - {angle}")
    for rec in report.recommendations:
        print(f"  \u2022 {rec}")

    # 3. Render LaTeX
    build_from_profile(profile_dict, template_path, output_path, header)
    print(f"\n[OK] Resume written to: {output_path}")


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

    artifacts = []
    for raw in args.artifacts:
        if ":" in raw:
            path, fmt = raw.rsplit(":", 1)
        else:
            path, fmt = raw, "blob"
        if fmt not in _PARSERS:
            parser.error(f"Unknown format '{fmt}'. Choose from: {list(_PARSERS)}")
        artifacts.append((path, fmt))

    header = {
        "name": args.name,
        "phone": args.phone,
        "email": args.email,
        "linkedin": args.linkedin,
        "github": args.github,
        "portfolio": args.portfolio,
    }

    run_pipeline(
        jd_path=args.jd,
        artifacts=artifacts,
        output_path=args.output,
        header=header,
        template_path=args.template,
        top_gaps=args.top_gaps,
    )


if __name__ == "__main__":
    main()
