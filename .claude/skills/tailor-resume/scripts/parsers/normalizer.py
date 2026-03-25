"""
normalizer.py
Shared utilities: date parsing, deduplication, format detection, profile merging.

Imported by latex_parser, plain_parser, pdf_extractor, docx_extractor, markdown_parser.
No local sibling imports — only stdlib and resume_types.
"""
from __future__ import annotations

import re
from typing import List, Tuple

from resume_types import Profile


def _dedupe(lst: List[str]) -> List[str]:
    """Remove duplicates while preserving insertion order."""
    return list(dict.fromkeys(lst))


def _parse_dates(date_str: str) -> Tuple[str, str]:
    """Split 'Jan 2022 – Present' or 'July 2024 -- Present' into (start, end)."""
    for sep in (" – ", " — ", " -- ", " - ", "–", "—", "--"):
        if sep in date_str:
            parts = date_str.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    return date_str.strip(), ""


def auto_detect_format(text: str) -> str:
    """Detect format from content heuristics. Returns 'latex'|'markdown'|'blob'."""
    if "\\documentclass" in text or "\\resumeSubheading" in text or "\\resumeItem" in text:
        return "latex"
    if re.search(r"^#{1,3}\s+\w", text, re.MULTILINE):
        return "markdown"
    return "blob"


def merge_profiles(*profiles: Profile) -> Profile:
    """Merge multiple parsed profiles into one canonical profile."""
    merged = Profile()
    for p in profiles:
        merged.experience.extend(p.experience)
        merged.projects.extend(p.projects)
        merged.skills.extend(p.skills)
        merged.education.extend(p.education)
        merged.certifications.extend(p.certifications)
    merged.skills = _dedupe(merged.skills)
    return merged
