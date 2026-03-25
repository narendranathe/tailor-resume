"""
markdown_parser.py
Parse Markdown resumes (## headings, - bullet lists) into a canonical Profile.

Expected format:
    ## Experience
    **Title** @ Company @ Jan 2022
    - bullet text
    ## Skills
    Python, SQL, Spark
"""
from __future__ import annotations

import re
from typing import Optional

from resume_types import Bullet, Profile, Role
from text_utils import extract_metrics, extract_tools, score_confidence


def parse_markdown(text: str, source: str = "markdown_resume") -> Profile:
    """Parse a markdown resume with ## headings and - bullet lists."""
    profile = Profile()
    lines = text.splitlines()
    section = ""
    current_role: Optional[Role] = None

    for line in lines:
        s = line.strip()
        if s.startswith("## "):
            section = s[3:].lower()
            continue
        if not s:
            continue

        if "experience" in section or "work" in section:
            role_match = re.match(r"\*\*(.+?)\*\*\s*[|@]\s*(.+?)\s*[|@]\s*(.+)", s)
            if role_match:
                current_role = Role(
                    title=role_match.group(1).strip(),
                    company=role_match.group(2).strip(),
                    start=role_match.group(3).strip(),
                    end="",
                    location="",
                )
                profile.experience.append(current_role)
                continue

            if (s.startswith("- ") or s.startswith("* ")) and current_role:
                txt = s[2:].strip()
                current_role.bullets.append(Bullet(
                    text=txt,
                    metrics=extract_metrics(txt),
                    tools=extract_tools(txt),
                    evidence_source=source,
                    confidence=score_confidence(txt),
                ))

        elif "skill" in section:
            for skill in re.split(r"[,|•]", s):
                sk = skill.strip(" -*")
                if sk:
                    profile.skills.append(sk)

    return profile
