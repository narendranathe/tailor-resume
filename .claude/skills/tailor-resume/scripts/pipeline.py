"""
pipeline.py
Shared orchestration logic for the tailor-resume pipeline.

Both cli.py and mcp_server.py delegate to this module.

Architecture:
    TailorConfig  — pure data: what to run (no I/O)
    TailorResult  — pure data: what came out (no I/O)
    execute()     — file-based pipeline (used by cli.py)
    execute_text() — in-memory pipeline (used by mcp_server.py)
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
    """Immutable configuration for a file-based pipeline run."""
    jd_text: str
    artifacts: List[Tuple[str, str]]   # (file_path, format)
    output_path: str
    header: Dict[str, str] = field(default_factory=dict)
    template_path: str = _DEFAULT_TEMPLATE
    top_gaps: int = 5
    cover_letter: bool = False
    user_id: str = ""


@dataclass
class TailorResult:
    """Immutable result from a pipeline run."""
    output_path: str
    ats_score: int
    gap_summary: List[str]
    profile_dict: Dict
    report: Optional[GapReport] = None
    cover_letter_tex: Optional[str] = None
    cover_letter_path: Optional[str] = None
    user_id: str = ""


# ---------------------------------------------------------------------------
# Core executors
# ---------------------------------------------------------------------------

def execute(config: TailorConfig) -> TailorResult:
    """Run the full pipeline from artifact files on disk."""
    if not config.artifacts:
        raise ValueError("At least one artifact is required.")

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

    resume_text = json.dumps(profile_dict)
    report = run_analysis(config.jd_text, resume_text, top_n=config.top_gaps)

    gap_lines: List[str] = [f"ATS Score: {report.ats_score_estimate}/100"]
    for i, gap in enumerate(report.top_missing, 1):
        gap_lines.append(f"{i}. [{gap.priority.upper()}] {gap.category}")
        gap_lines.append(f"   Missing: {', '.join(gap.jd_keywords[:5])}")
        for angle in gap.suggested_angles:
            gap_lines.append(f"     - {angle}")
    for rec in report.recommendations:
        gap_lines.append(f"  • {rec}")

    Path(config.output_path).parent.mkdir(parents=True, exist_ok=True)
    build_from_profile(profile_dict, config.template_path, config.output_path, config.header)

    cover_letter_tex: Optional[str] = None
    cover_letter_path: Optional[str] = None
    if config.cover_letter:
        from cover_letter_renderer import build_cover_letter  # noqa: E402
        cover_letter_tex = build_cover_letter(
            profile_dict, report, config.header, jd_text=config.jd_text
        )
        cover_letter_path = str(Path(config.output_path).parent / "cover_letter.tex")
        Path(cover_letter_path).write_text(cover_letter_tex, encoding="utf-8")

    return TailorResult(
        output_path=config.output_path,
        ats_score=report.ats_score_estimate,
        gap_summary=gap_lines,
        profile_dict=profile_dict,
        report=report,
        cover_letter_tex=cover_letter_tex,
        cover_letter_path=cover_letter_path,
        user_id=config.user_id,
    )


def execute_text(
    jd_text: str,
    artifact_text: str,
    artifact_format: str = "blob",
    output_path: str = "out/resume.tex",
    header: Optional[Dict[str, str]] = None,
    template_path: str = _DEFAULT_TEMPLATE,
    top_gaps: int = 5,
    cover_letter: bool = False,
    user_id: str = "",
) -> TailorResult:
    """
    Pipeline variant for callers who have resume text in memory (not a file).
    Used by mcp_server.py where the tool receives raw text over the wire.
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

    cover_letter_tex: Optional[str] = None
    cover_letter_path: Optional[str] = None
    if cover_letter:
        from cover_letter_renderer import build_cover_letter  # noqa: E402
        cover_letter_tex = build_cover_letter(
            profile_dict, report, header or {}, jd_text=jd_text
        )
        cover_letter_path = str(Path(output_path).parent / "cover_letter.tex")
        Path(cover_letter_path).write_text(cover_letter_tex, encoding="utf-8")

    return TailorResult(
        output_path=output_path,
        ats_score=report.ats_score_estimate,
        gap_summary=gap_lines,
        profile_dict=profile_dict,
        report=report,
        cover_letter_tex=cover_letter_tex,
        cover_letter_path=cover_letter_path,
        user_id=user_id,
    )
