"""
latex_renderer.py
Renders a LaTeX resume from a canonical profile dict + template.
All PII is runtime-injected — never hardcoded.

Template placeholders use {{KEY}} syntax.

Usage:
    python latex_renderer.py --profile profile.json --template ../templates/resume_template.tex --output resume.tex
"""
from __future__ import annotations

import argparse
import json
import re
import textwrap
from pathlib import Path
from typing import Dict, List


# ---------------------------------------------------------------------------
# LaTeX escaping
# ---------------------------------------------------------------------------
_LATEX_SPECIAL = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\^{}",
    "\\": r"\textbackslash{}",
}


def escape(text: str) -> str:
    """Escape special LaTeX characters in plain text."""
    return "".join(_LATEX_SPECIAL.get(c, c) for c in text)


def escape_url(url: str) -> str:
    """URLs go inside href — only escape % and # outside the url arg."""
    return url


# ---------------------------------------------------------------------------
# Profile → LaTeX block builders
# ---------------------------------------------------------------------------

def render_bullets(bullets: List[Dict]) -> str:
    lines = ["    \\resumeItemListStart"]
    for b in bullets[:6]:  # max 6 bullets per role
        text = escape(b.get("text", ""))
        lines.append(f"      \\resumeItem{{{text}}}")
    lines.append("    \\resumeItemListEnd")
    return "\n".join(lines)


def render_experience(experience: List[Dict]) -> str:
    blocks = ["\\section{Experience}", "  \\resumeSubHeadingListStart", ""]
    for role in experience:
        title = escape(role.get("title", ""))
        company = escape(role.get("company", ""))
        start = escape(role.get("start", ""))
        end = escape(role.get("end", "Present"))
        location = escape(role.get("location", ""))
        date_range = f"{start} -- {end}" if start else end

        blocks.append(
            f"    \\resumeSubheading\n"
            f"      {{{title}}}{{{date_range}}}\n"
            f"      {{{company}}}{{{location}}}"
        )
        bullets = role.get("bullets", [])
        if bullets:
            blocks.append(render_bullets(bullets))
        blocks.append("")

    blocks.append("  \\resumeSubHeadingListEnd")
    return "\n".join(blocks)


def render_projects(projects: List[Dict]) -> str:
    if not projects:
        return ""
    blocks = ["\\section{Projects}", "    \\resumeSubHeadingListStart", ""]
    for proj in projects:
        name = escape(proj.get("name", ""))
        tech = escape(", ".join(proj.get("tech", [])))
        date = escape(proj.get("date", ""))
        heading = f"\\textbf{{{name}}} $|$ \\emph{{{tech}}}"
        blocks.append(
            f"      \\resumeProjectHeading\n"
            f"          {{{heading}}}{{{date}}}"
        )
        bullets = proj.get("bullets", [])
        if bullets:
            blocks.append(render_bullets(bullets))
        blocks.append("")
    blocks.append("    \\resumeSubHeadingListEnd")
    return "\n".join(blocks)


def render_skills(skills_data) -> str:
    """
    skills_data: either a list of strings or a dict with categories.
    """
    if isinstance(skills_data, list):
        # Plain list — output as a single skills line
        skill_str = escape(", ".join(skills_data))
        return (
            "\\section{Technical Skills}\n"
            " \\begin{itemize}[leftmargin=0.15in, label={}]\n"
            "    \\small{\\item{\n"
            f"     \\textbf{{Skills}}{{: {skill_str}}}\n"
            "    }}\n"
            " \\end{itemize}"
        )

    if isinstance(skills_data, dict):
        lines = [
            "\\section{Technical Skills}",
            " \\begin{itemize}[leftmargin=0.15in, label={}]",
            "    \\small{\\item{",
        ]
        items = []
        for category, values in skills_data.items():
            val_str = escape(", ".join(values) if isinstance(values, list) else str(values))
            items.append(f"     \\textbf{{{escape(category)}}}{{: {val_str}}}")
        lines.append(" \\\\\n".join(items))
        lines += ["    }}", " \\end{itemize}"]
        return "\n".join(lines)

    return ""


def render_education(education: List[Dict]) -> str:
    blocks = ["\\section{Education}", "  \\resumeSubHeadingListStart"]
    for edu in education:
        school = escape(edu.get("school", edu.get("institution", "")))
        location = escape(edu.get("location", ""))
        degree = escape(edu.get("degree", ""))
        dates = escape(edu.get("dates", edu.get("date", "")))
        blocks.append(
            f"    \\resumeSubheading\n"
            f"      {{{school}}}{{{location}}}\n"
            f"      {{{degree}}}{{{dates}}}"
        )
    blocks.append("  \\resumeSubHeadingListEnd")
    return "\n".join(blocks)


def render_certifications(certs: List[str]) -> str:
    if not certs:
        return ""
    cert_str = " $|$ ".join(escape(c) for c in certs)
    return (
        "\\section{Certifications}\n"
        " \\begin{itemize}[leftmargin=0.15in, label={}]\n"
        f"    \\small{{\\item{{ {cert_str} }}}}\n"
        " \\end{itemize}"
    )


# ---------------------------------------------------------------------------
# Template renderer
# ---------------------------------------------------------------------------

def render_template(template_path: str, output_path: str, replacements: Dict[str, str]) -> None:
    """Replace {{KEY}} placeholders in template with rendered values."""
    content = Path(template_path).read_text(encoding="utf-8")
    for key, value in replacements.items():
        content = content.replace(f"{{{{{key}}}}}", value)

    # Warn about any remaining unfilled placeholders
    remaining = re.findall(r"\{\{[A-Z_]+\}\}", content)
    if remaining:
        print(f"[WARNING] Unfilled placeholders: {remaining}")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(content, encoding="utf-8")
    print(f"[OK] Resume written to: {output_path}")


def build_from_profile(
    profile: Dict,
    template_path: str = "../templates/resume_template.tex",
    output_path: str = "resume.tex",
    header: Dict | None = None,
) -> None:
    """
    Build a complete resume.tex from a profile dict.

    header dict keys (all runtime-provided, never hardcoded):
        name, phone, email, linkedin, github, portfolio
    """
    h = header or {}

    replacements: Dict[str, str] = {
        "NAME": escape(h.get("name", "Your Name")),
        "PHONE": escape(h.get("phone", "")),
        "EMAIL": h.get("email", ""),
        "LINKEDIN_URL": h.get("linkedin", ""),
        "LINKEDIN_DISPLAY": h.get("linkedin", "").replace("https://", ""),
        "GITHUB_URL": h.get("github", ""),
        "GITHUB_DISPLAY": h.get("github", "").replace("https://", ""),
        "PORTFOLIO_URL": h.get("portfolio", ""),
        "PORTFOLIO_DISPLAY": h.get("portfolio", "").replace("https://", ""),
        "EDUCATION_SECTION": render_education(profile.get("education", [])),
        "EXPERIENCE_SECTION": render_experience(profile.get("experience", [])),
        "PROJECTS_SECTION": render_projects(profile.get("projects", [])),
        "SKILLS_SECTION": render_skills(profile.get("skills", [])),
        "CERTIFICATIONS_SECTION": render_certifications(profile.get("certifications", [])),
        "SUMMARY": escape(profile.get("summary", "")),
    }

    render_template(template_path, output_path, replacements)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Render LaTeX resume from profile JSON.")
    parser.add_argument("--profile", required=True, help="Path to profile JSON")
    parser.add_argument(
        "--template",
        default=str(Path(__file__).parent.parent / "templates" / "resume_template.tex"),
        help="Path to LaTeX template",
    )
    parser.add_argument("--output", default="resume.tex", help="Output .tex path")
    parser.add_argument("--name", default="", help="Full name (runtime PII)")
    parser.add_argument("--phone", default="", help="Phone (runtime PII)")
    parser.add_argument("--email", default="", help="Email (runtime PII)")
    parser.add_argument("--linkedin", default="", help="LinkedIn URL (runtime PII)")
    parser.add_argument("--github", default="", help="GitHub URL (runtime PII)")
    parser.add_argument("--portfolio", default="", help="Portfolio URL (runtime PII)")
    args = parser.parse_args()

    with open(args.profile, encoding="utf-8") as f:
        profile = json.load(f)

    header = {
        "name": args.name,
        "phone": args.phone,
        "email": args.email,
        "linkedin": args.linkedin,
        "github": args.github,
        "portfolio": args.portfolio,
    }

    build_from_profile(profile, args.template, args.output, header)


if __name__ == "__main__":
    main()
