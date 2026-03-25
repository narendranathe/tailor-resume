"""
latex_parser.py
Parse LaTeX resumes (Jake/Sourabh/standard templates) into a canonical Profile.

Handles:
  - \\resumeSubheading{Title}{Dates}{Company}{Location}
  - \\resumeItem{bullet text} with nested \\href / \\textbf
  - \\resumeProjectHeading{Name | Tech}{Date}
  - \\section{Experience|Projects|Education|Skills}
  - Skills extracted from \\textbf{Category}: items
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from resume_types import Bullet, Profile, Project, Role
from text_utils import extract_metrics, extract_tools, score_confidence
from parsers.normalizer import _dedupe, _parse_dates


# ---------------------------------------------------------------------------
# LaTeX utilities — brace-counting to handle multi-line commands
# ---------------------------------------------------------------------------

def _extract_args(text: str, pos: int, n: int) -> Tuple[List[str], int]:
    """
    Extract n brace-delimited arguments from text starting at pos,
    skipping whitespace between arguments.
    Returns (list of arg strings, position after last closing brace).
    Handles nested braces (e.g. \\href{url}{label} inside \\resumeItem{...}).
    """
    args: List[str] = []
    i = pos
    while len(args) < n and i < len(text):
        while i < len(text) and text[i] in " \t\n\r":
            i += 1
        if i >= len(text) or text[i] != "{":
            break
        depth = 0
        start = i + 1
        while i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    args.append(text[start:i])
                    i += 1
                    break
            i += 1
    return args, i


def _clean_latex(text: str) -> str:
    """Strip LaTeX macros and escapes, returning readable plain text."""
    # Unwrap common formatting commands: \textbf{x} \textit{x} \emph{x} \small{x} etc.
    for _ in range(4):  # iterate to handle nested commands
        text = re.sub(r"\\(?:textbf|textit|emph|underline|small|large|tiny|huge|scshape)\{([^{}]*)\}", r"\1", text)
    # Unwrap \href{url}{label} -> label
    text = re.sub(r"\\href\{[^{}]*\}\{([^{}]*)\}", r"\1", text)
    # Unwrap \url{...} -> (url)
    text = re.sub(r"\\url\{([^{}]*)\}", r"(\1)", text)
    # Remove remaining \command{...} wrappers (single level)
    text = re.sub(r"\\[a-zA-Z]+\{([^{}]*)\}", r"\1", text)
    # Remove lone \command
    text = re.sub(r"\\[a-zA-Z@]+\*?", " ", text)
    # Normalize LaTeX special chars
    text = text.replace("\\%", "%").replace("\\$", "$").replace("\\_", "_")
    text = text.replace("\\&", "&").replace("\\#", "#").replace("\\~", "~")
    text = text.replace("---", "—").replace("--", "–")
    return re.sub(r"\s+", " ", text).strip()


def _split_sections_latex(text: str) -> dict:
    """
    Split a LaTeX resume into named sections using \\section{Name}.
    Returns {section_name_lower: section_body_text}.
    """
    section_re = re.compile(r"\\section\{([^}]+)\}", re.IGNORECASE)
    matches = list(section_re.finditer(text))
    sections: dict = {}
    for idx, m in enumerate(matches):
        name = m.group(1).lower().strip()
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        sections[name] = text[start:end]
    return sections


def _attach_bullets_to_roles(body: str, roles: List[Role], source: str) -> None:
    """Find all \\resumeItem{} in body and attach them to the correct role by position."""
    if not roles:
        return
    sub_positions: List[int] = [m.start() for m in re.finditer(r"\\resumeSubheading", body)]
    for m in re.finditer(r"\\resumeItem", body):
        item_pos = m.start()
        args, _ = _extract_args(body, m.end(), 1)
        if not args:
            continue
        txt = _clean_latex(args[0])
        if not txt:
            continue
        role_idx = 0
        for i, sp in enumerate(sub_positions):
            if sp <= item_pos:
                role_idx = i
        if role_idx < len(roles):
            bullet = Bullet(
                text=txt,
                metrics=extract_metrics(txt),
                tools=extract_tools(txt),
                evidence_source=source,
                confidence=score_confidence(txt),
            )
            roles[role_idx].bullets.append(bullet)


def _attach_bullets_to_projects(body: str, projects: List[Project], source: str) -> None:
    """Attach \\resumeItem{} bullets to the correct project by position."""
    if not projects:
        return
    sub_positions: List[int] = [m.start() for m in re.finditer(r"\\resumeProjectHeading", body)]
    for m in re.finditer(r"\\resumeItem", body):
        item_pos = m.start()
        args, _ = _extract_args(body, m.end(), 1)
        if not args:
            continue
        txt = _clean_latex(args[0])
        if not txt:
            continue
        proj_idx = 0
        for i, sp in enumerate(sub_positions):
            if sp <= item_pos:
                proj_idx = i
        if proj_idx < len(projects):
            bullet = Bullet(
                text=txt,
                metrics=extract_metrics(txt),
                tools=extract_tools(txt),
                evidence_source=source,
                confidence=score_confidence(txt),
            )
            projects[proj_idx].bullets.append(bullet)


def parse_latex(text: str, source: str = "latex_resume") -> Profile:
    """
    Parse a LaTeX resume (Jake/Sourabh/standard template).
    Uses brace-counting so multi-line \\resumeSubheading args are handled correctly.
    Supports nested macros like \\href inside \\resumeItem.
    """
    profile = Profile()
    sections = _split_sections_latex(text)

    # ---- Experience --------------------------------------------------------
    exp_body = sections.get("experience", "") or sections.get("work experience", "")
    current_role: Optional[Role] = None

    for m in re.finditer(r"\\resumeSubheading", exp_body):
        args, _ = _extract_args(exp_body, m.end(), 4)
        if len(args) < 3:
            continue
        title   = _clean_latex(args[0])
        dates   = _clean_latex(args[1])
        company = _clean_latex(args[2])
        location = _clean_latex(args[3]) if len(args) > 3 else ""
        start, end = _parse_dates(dates)
        current_role = Role(title=title, company=company, start=start, end=end, location=location)
        profile.experience.append(current_role)

    _attach_bullets_to_roles(exp_body, profile.experience, source)

    # ---- Projects ----------------------------------------------------------
    proj_body = sections.get("projects", "") or sections.get("personal projects", "")
    current_proj: Optional[Project] = None

    for m in re.finditer(r"\\resumeProjectHeading", proj_body):
        args, _ = _extract_args(proj_body, m.end(), 2)
        if not args:
            continue
        raw_name = _clean_latex(args[0])
        parts = re.split(r"\$?\|\$?", raw_name, maxsplit=1)
        name = parts[0].strip()
        tech_str = parts[1].strip() if len(parts) > 1 else ""
        date = _clean_latex(args[1]) if len(args) > 1 else ""
        tech = [t.strip() for t in re.split(r"[,;]", tech_str) if t.strip()]
        current_proj = Project(name=name, tech=tech, date=date)
        profile.projects.append(current_proj)

    _attach_bullets_to_projects(proj_body, profile.projects, source)

    # ---- Education ---------------------------------------------------------
    edu_body = sections.get("education", "")
    for m in re.finditer(r"\\resumeSubheading", edu_body):
        args, _ = _extract_args(edu_body, m.end(), 4)
        if len(args) < 2:
            continue
        # Jake/standard template arg order: {institution}{location}{degree}{dates}
        profile.education.append({
            "institution": _clean_latex(args[0]),
            "location": _clean_latex(args[1]),
            "degree": _clean_latex(args[2]) if len(args) > 2 else "",
            "dates": _clean_latex(args[3]) if len(args) > 3 else "",
        })

    # ---- Skills ------------------------------------------------------------
    skills_body = ""
    for key in ("technical skills", "skills", "technologies"):
        if key in sections:
            skills_body = sections[key]
            break
    if skills_body:
        for m in re.finditer(r"\\textbf\{([^}]+)\}\{?:?\}?\s*([^\\\n]+)", skills_body):
            vals = m.group(2)
            for sk in re.split(r"[,;]", vals):
                sk = sk.strip(" \\{}$|")
                if sk and len(sk) > 1:
                    profile.skills.append(sk)
        if not profile.skills:
            for sk in re.split(r"[,;\n]", _clean_latex(skills_body)):
                sk = sk.strip(" -*•|")
                if sk and len(sk) > 1:
                    profile.skills.append(sk)
        profile.skills = _dedupe(profile.skills)

    # ---- Certifications & Publications -------------------------------------
    cert_body = ""
    for key in sections:
        if "cert" in key or "publication" in key or "recognition" in key:
            cert_body += sections[key] + "\n"
    if cert_body:
        cleaned = _clean_latex(cert_body)
        for line in cleaned.splitlines():
            line = line.strip(" -•*|")
            if line and len(line) > 4:
                profile.certifications.append(line)

    return profile
