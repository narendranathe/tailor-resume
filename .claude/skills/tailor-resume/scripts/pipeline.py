"""
pipeline.py
Shared orchestration logic for the tailor-resume pipeline.

Previously duplicated between cli.py and mcp_server.py.  Both now delegate to
this module, keeping the pipeline execution logic in one place.

Architecture:
    TailorConfig  — pure data: what to run (no I/O)
    TailorResult  — pure data: what came out (no I/O)
    execute()     — side-effect boundary: file reads, gap analysis, LaTeX write
    cli.py        — thin shell: argparse → TailorConfig → execute()
    mcp_server.py — thin shell: MCP tool args → TailorConfig → execute()

Usage (from code):
    from pipeline import TailorConfig, TailorResult, execute

    config = TailorConfig(
        jd_text=open("jd.txt").read(),
        artifacts=[("resume.md", "markdown")],
        output_path="out/resume.tex",
        header={"name": "Jane", "email": "jane@example.com"},
    )
    result = execute(config)
    print(result.ats_score)
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Make sibling scripts importable when imported from a different CWD
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
from resume_types import GapReport, profile_to_dict  # noqa: E402

_PARSERS: Dict[str, object] = {
    "blob": parse_blob,
    "markdown": parse_markdown,
    "latex": parse_latex,
    "linkedin": parse_linkedin,
}

_DEFAULT_TEMPLATE = str(
    Path(__file__).parent.parent / "templates" / "resume_template.tex"
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TailorConfig:
    """
    Immutable configuration for a single pipeline run.

    Attributes:
        jd_text:       Full job-description text (not a file path).
        artifacts:     List of (file_path, format) tuples.
                       format ∈ {blob, markdown, latex, linkedin}.
        output_path:   Where to write the rendered resume.tex.
        header:        Dict with PII keys: name, email, phone, linkedin,
                       github, portfolio.  Values may be empty strings.
        template_path: Path to the LaTeX template file.
        top_gaps:      Number of top gap signals to include in the result.
    """
    jd_text: str
    artifacts: List[Tuple[str, str]]
    output_path: str
    header: Dict[str, str] = field(default_factory=dict)
    template_path: str = _DEFAULT_TEMPLATE
    top_gaps: int = 5


@dataclass
class TailorResult:
    """
    Immutable result from a pipeline run.

    Attributes:
        output_path:   The path where resume.tex was written.
        ats_score:     Estimated ATS match score (0–100).
        gap_summary:   Human-readable gap analysis lines for display.
        profile_dict:  The merged, parsed profile as a plain dict.
        report:        Full GapReport dataclass (for programmatic access).
    """
    output_path: str
    ats_score: int
    gap_summary: List[str]
    profile_dict: Dict
    report: Optional[GapReport] = None


# ---------------------------------------------------------------------------
# Core executor
# ---------------------------------------------------------------------------

def execute(config: TailorConfig) -> TailorResult:
    """
    Run the full tailor-resume pipeline.

    1. Parse all input artifacts and merge into one Profile.
    2. Run gap analysis against the JD.
    3. Render the LaTeX resume.
    4. Return a TailorResult with scores and paths.

    Raises:
        ValueError: if no artifacts are provided or a format is unknown.
        FileNotFoundError: if an artifact path does not exist.
    """
    if not config.artifacts:
        raise ValueError("At least one artifact is required.")

    # 1. Parse and merge artifacts
    profiles = []
    for path, fmt in config.artifacts:
        parser = _PARSERS.get(fmt)
        if parser is None:
            raise ValueError(f"Unknown artifact format '{fmt}'. Use: {list(_PARSERS)}")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        profiles.append(parser(text))  # type: ignore[operator]

    profile = merge_profiles(*profiles) if len(profiles) > 1 else profiles[0]
    profile_dict = profile_to_dict(profile)

    # 2. Gap analysis
    resume_text = json.dumps(profile_dict)
    report = run_analysis(config.jd_text, resume_text, top_n=config.top_gaps)

    # Build human-readable gap summary lines
    gap_lines: List[str] = [f"ATS Score: {report.ats_score_estimate}/100"]
    for i, gap in enumerate(report.top_missing, 1):
        gap_lines.append(f"{i}. [{gap.priority.upper()}] {gap.category}")
        gap_lines.append(f"   Missing: {', '.join(gap.jd_keywords[:5])}")
        for angle in gap.suggested_angles:
            gap_lines.append(f"     - {angle}")
    for rec in report.recommendations:
        gap_lines.append(f"  • {rec}")

    # 3. Render LaTeX
    Path(config.output_path).parent.mkdir(parents=True, exist_ok=True)
    build_from_profile(profile_dict, config.template_path, config.output_path, config.header)

    return TailorResult(
        output_path=config.output_path,
        ats_score=report.ats_score_estimate,
        gap_summary=gap_lines,
        profile_dict=profile_dict,
        report=report,
    )


def execute_text(
    jd_text: str,
    artifact_text: str,
    artifact_format: str = "blob",
    output_path: str = "out/resume.tex",
    header: Optional[Dict[str, str]] = None,
    template_path: str = _DEFAULT_TEMPLATE,
    top_gaps: int = 5,
) -> TailorResult:
    """
    Pipeline variant for callers who have resume text in memory (not a file).

    Used by mcp_server.py where the tool receives raw text over the wire.
    Avoids writing a temp file — parses the text directly.
    """
    parser = _PARSERS.get(artifact_format)
    if parser is None:
        raise ValueError(f"Unknown artifact format '{artifact_format}'. Use: {list(_PARSERS)}")

    profile = parser(artifact_text)  # type: ignore[operator]
    profile_dict = profile_to_dict(profile)

    resume_json = json.dumps(profile_dict)
    report = run_analysis(jd_text, resume_json, top_n=top_gaps)

    gap_lines: List[str] = [f"ATS Score: {report.ats_score_estimate}/100"]
    for i, gap in enumerate(report.top_missing, 1):
        gap_lines.append(f"{i}. [{gap.priority.upper()}] {gap.category}")
        gap_lines.append(f"   Missing: {', '.join(gap.jd_keywords[:5])}")
        for angle in gap.suggested_angles:
            gap_lines.append(f"     - {angle}")
    for rec in report.recommendations:
        gap_lines.append(f"  • {rec}")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    build_from_profile(profile_dict, template_path, output_path, header or {})

    return TailorResult(
        output_path=output_path,
        ats_score=report.ats_score_estimate,
        gap_summary=gap_lines,
        profile_dict=profile_dict,
        report=report,
    )
