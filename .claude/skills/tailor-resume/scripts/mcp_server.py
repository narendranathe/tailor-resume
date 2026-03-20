"""
mcp_server.py
MCP server for the tailor-resume pipeline.

Exposes four tools that Claude Code can call directly:
  - extract_profile   parse resume text -> profile JSON
  - analyze_gap       JD vs profile -> gap report JSON
  - render_latex      profile + header -> writes resume.tex
  - run_pipeline      full pipeline in one call

Usage (stdio, for Claude Code):
    python mcp_server.py

Config in .claude/.mcp.json:
    {
      "mcpServers": {
        "tailor-resume": {
          "command": "python",
          "args": [".claude/skills/tailor-resume/scripts/mcp_server.py"]
        }
      }
    }
"""
from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from dataclasses import asdict
from pathlib import Path

# Make sibling scripts importable when run from repo root
_SCRIPTS = Path(__file__).parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from jd_gap_analyzer import run_analysis  # noqa: E402
from latex_renderer import build_from_profile  # noqa: E402
from profile_extractor import (  # noqa: E402
    parse_blob,
    parse_latex,
    parse_linkedin,
    parse_markdown,
)
from resume_types import profile_to_dict  # noqa: E402

mcp = FastMCP("tailor-resume")

_PARSERS = {
    "blob": parse_blob,
    "markdown": parse_markdown,
    "latex": parse_latex,
    "linkedin": parse_linkedin,
}

_DEFAULT_TEMPLATE = str(
    Path(__file__).parent.parent / "templates" / "resume_template.tex"
)


# ---------------------------------------------------------------------------
# Tool 1: extract_profile
# ---------------------------------------------------------------------------
@mcp.tool()
def extract_profile(text: str, format: str = "blob") -> str:  # noqa: A002
    """
    Parse a resume artifact (plain text, markdown, LaTeX, or LinkedIn PDF paste)
    into a structured profile JSON.

    Args:
        text: Raw resume text — blob, markdown, LaTeX source, or LinkedIn PDF export.
        format: Input format. One of: blob | markdown | latex | linkedin.
                Default is 'blob' (free-form text with Company:/Title: headers).

    Returns:
        JSON string with keys: experience, projects, skills, education, certifications.
        Each experience role has: title, company, start, end, location, bullets.
        Each bullet has: text, metrics, tools, evidence_source, confidence.
        On error: {"error": "<message>"}
    """
    try:
        if not text or not text.strip():
            return json.dumps({"error": "text must not be empty"})
        fmt = format.lower()
        if fmt not in _PARSERS:
            return json.dumps({"error": f"unknown format: {format}. Use: {list(_PARSERS)}"})
        profile = _PARSERS[fmt](text)
        return json.dumps(asdict(profile), indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# Tool 2: analyze_gap
# ---------------------------------------------------------------------------
@mcp.tool()
def analyze_gap(jd_text: str, resume_text: str, top_n: int = 5) -> str:
    """
    Analyze a job description against a candidate profile and return a
    prioritized gap report.

    Args:
        jd_text: Full text of the job description.
        resume_text: Candidate profile — either raw text or JSON string from
                     extract_profile. Both formats are accepted.
        top_n: Number of top gap signals to include in the report (default 5).

    Returns:
        JSON string with keys:
          - ats_score_estimate (0-100): rough ATS keyword match score
          - top_missing: list of gap signals, each with category, priority
            (high/medium/low), jd_keywords, resume_coverage (0-1),
            and suggested_angles (concrete prompts for filling the gap)
          - keyword_gaps: list of [keyword, jd_frequency] pairs missing from resume
          - recommendations: list of actionable strings
          On error: {"error": "<message>"}
    """
    try:
        if not jd_text or not jd_text.strip():
            return json.dumps({"error": "jd_text must not be empty"})
        if not resume_text or not resume_text.strip():
            return json.dumps({"error": "resume_text must not be empty"})
        report = run_analysis(jd_text, resume_text, top_n=top_n)
        return json.dumps(asdict(report), indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# Tool 3: render_latex
# ---------------------------------------------------------------------------
@mcp.tool()
def render_latex(
    profile_json: str,
    output_path: str = "out/resume.tex",
    name: str = "",
    email: str = "",
    phone: str = "",
    linkedin: str = "",
    github: str = "",
    portfolio: str = "",
) -> str:
    """
    Render a LaTeX resume from a structured profile JSON.

    Args:
        profile_json: JSON string from extract_profile (or hand-crafted dict).
        output_path: Where to write resume.tex. Created with parent dirs.
                     Default: out/resume.tex relative to cwd.
        name: Full name (injected at runtime — never hardcoded in template).
        email: Email address.
        phone: Phone number.
        linkedin: LinkedIn profile URL.
        github: GitHub profile URL.
        portfolio: Portfolio/website URL.

    Returns:
        JSON string with keys:
          - output_path: absolute path to the written .tex file
          - warnings: list of any unfilled placeholder warnings
          - message: human-readable status
          On error: {"error": "<message>"}
    """
    try:
        if not profile_json or not profile_json.strip():
            return json.dumps({"error": "profile_json must not be empty"})
        try:
            profile = json.loads(profile_json)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"invalid profile JSON: {e}"})

        header = {
            "name": name, "email": email, "phone": phone,
            "linkedin": linkedin, "github": github, "portfolio": portfolio,
        }

        buf = io.StringIO()
        with redirect_stdout(buf):
            build_from_profile(profile, _DEFAULT_TEMPLATE, output_path, header)

        warnings = [ln for ln in buf.getvalue().splitlines() if "WARNING" in ln]
        abs_path = str(Path(output_path).resolve())
        return json.dumps({
            "output_path": abs_path,
            "warnings": warnings,
            "message": f"Resume written to {abs_path}. Compile with pdflatex or upload to Overleaf.",
        }, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# Tool 4: run_pipeline
# ---------------------------------------------------------------------------
@mcp.tool()
def run_pipeline(
    jd_text: str,
    artifact_text: str,
    artifact_format: str = "blob",
    output_path: str = "out/resume.tex",
    name: str = "",
    email: str = "",
    phone: str = "",
    linkedin: str = "",
    github: str = "",
    portfolio: str = "",
    top_gaps: int = 5,
) -> str:
    """
    Full tailor-resume pipeline in a single call.

    Chains: extract_profile -> analyze_gap -> render_latex.

    Args:
        jd_text: Full text of the job description.
        artifact_text: Resume text to parse (blob, markdown, LaTeX, or LinkedIn export).
        artifact_format: Format of artifact_text. One of: blob|markdown|latex|linkedin.
        output_path: Where to write resume.tex. Default: out/resume.tex.
        name / email / phone / linkedin / github / portfolio: Runtime PII for header.
        top_gaps: Number of gap signals to include in the report.

    Returns:
        JSON string with keys:
          - profile: extracted profile dict
          - gap_report: dict with ats_score_estimate, top_missing, keyword_gaps, recommendations
          - output_path: absolute path to written resume.tex
          - warnings: any render warnings
          On error: {"error": "<message>"}
    """
    try:
        if not jd_text or not jd_text.strip():
            return json.dumps({"error": "jd_text must not be empty"})
        if not artifact_text or not artifact_text.strip():
            return json.dumps({"error": "artifact_text must not be empty"})
        fmt = artifact_format.lower()
        if fmt not in _PARSERS:
            return json.dumps({"error": f"unknown format: {artifact_format}. Use: {list(_PARSERS)}"})

        # 1. Parse
        profile = _PARSERS[fmt](artifact_text)
        profile_dict = profile_to_dict(profile)

        # 2. Gap analysis
        resume_text = json.dumps(profile_dict)
        report = run_analysis(jd_text, resume_text, top_n=top_gaps)
        report_dict = asdict(report)

        # 3. Render
        header = {
            "name": name, "email": email, "phone": phone,
            "linkedin": linkedin, "github": github, "portfolio": portfolio,
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            build_from_profile(profile_dict, _DEFAULT_TEMPLATE, output_path, header)

        warnings = [ln for ln in buf.getvalue().splitlines() if "WARNING" in ln]
        return json.dumps({
            "profile": profile_dict,
            "gap_report": report_dict,
            "output_path": str(Path(output_path).resolve()),
            "warnings": warnings,
        }, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


if __name__ == "__main__":
    mcp.run()
