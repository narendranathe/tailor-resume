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

Artifact format: <path>:<format>
    Formats: blob | markdown | latex | linkedin
    Default format if omitted: blob
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

_VALID_FORMATS = {"blob", "markdown", "latex", "linkedin"}

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

    # Validate and parse artifact strings
    artifacts = []
    for raw in args.artifacts:
        if ":" in raw:
            path, fmt = raw.rsplit(":", 1)
        else:
            path, fmt = raw, "blob"
        if fmt not in _VALID_FORMATS:
            parser.error(f"Unknown format '{fmt}'. Choose from: {sorted(_VALID_FORMATS)}")
        artifacts.append((path, fmt))

    with open(args.jd, encoding="utf-8") as f:
        jd_text = f.read()

    config = TailorConfig(
        jd_text=jd_text,
        artifacts=artifacts,
        output_path=args.output,
        header={
            "name": args.name,
            "phone": args.phone,
            "email": args.email,
            "linkedin": args.linkedin,
            "github": args.github,
            "portfolio": args.portfolio,
        },
        template_path=args.template,
        top_gaps=args.top_gaps,
    )

    result = execute(config)

    print("\n=== Gap Analysis ===")
    for line in result.gap_summary:
        print(line)
    print(f"\n[OK] Resume written to: {result.output_path}")


if __name__ == "__main__":
    main()
