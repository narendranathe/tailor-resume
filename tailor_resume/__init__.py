"""
tailor-resume — ATS-optimized resume tailoring from the command line.

Usage:
    tailor-resume --jd jd.txt --artifact resume.md --name "Jane Smith" --email "jane@example.com"

Python API:
    from tailor_resume import extract_profile, analyze_gap, render_latex, run_pipeline
"""
from __future__ import annotations

import sys
import os

# Add the bundled scripts to the path so imports resolve without a separate install step.
_SCRIPTS = os.path.join(os.path.dirname(__file__), "_scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from profile_extractor import (  # noqa: E402
    parse_blob, parse_markdown, parse_latex, parse_linkedin,
    parse_pdf, parse_docx, auto_detect_format,
)
from jd_gap_analyzer import run_analysis  # noqa: E402
from latex_renderer import build_from_profile  # noqa: E402
from cli import main as _pipeline_main  # noqa: E402

__all__ = [
    "extract_profile",
    "analyze_gap",
    "render_latex",
    "run_pipeline",
]

_PARSERS = {
    "blob": parse_blob,
    "markdown": parse_markdown,
    "latex": parse_latex,
    "linkedin": parse_linkedin,
}


def extract_profile(text: str, format: str = "blob"):
    """Parse resume text into a structured Profile object."""
    parser = _PARSERS.get(format, parse_blob)
    return parser(text)


def analyze_gap(jd_text: str, resume_text: str, top_n: int = 5):
    """Score a resume against a job description and return a GapReport."""
    return run_analysis(jd_text, resume_text, top_n=top_n)


_DEFAULT_TEMPLATE = os.path.join(os.path.dirname(__file__), "_templates", "resume_template.tex")


def render_latex(profile, header: dict | None = None, template_path: str | None = None) -> str:
    """Render a tailored single-page LaTeX resume from a profile."""
    from dataclasses import asdict
    profile_dict = asdict(profile) if hasattr(profile, "__dataclass_fields__") else profile
    return build_from_profile(
        profile_dict,
        header=header or {},
        template_path=template_path or _DEFAULT_TEMPLATE,
    )


def run_pipeline(jd_text: str, artifact_text: str, artifact_format: str = "blob",
                 output_path: str = "out/resume.tex", **header_kwargs) -> dict:
    """Full pipeline: parse → gap analysis → render LaTeX. Returns result dict."""
    import json
    from pathlib import Path
    from dataclasses import asdict

    profile = extract_profile(artifact_text, artifact_format)
    gap_report = analyze_gap(jd_text, artifact_text)
    header = {k: v for k, v in header_kwargs.items() if v}
    tex = render_latex(profile, header=header)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(tex, encoding="utf-8")
    return {
        "profile": asdict(profile),
        "gap_report": asdict(gap_report),
        "output_path": output_path,
        "ats_score": gap_report.ats_score_estimate,
    }
