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
    """Remove duplicates while preserving insertion order, case-insensitively.

    The first-seen casing is kept.  For example:
        ["Python", "python", "SQL", "sql"] → ["Python", "SQL"]
    """
    seen: set = set()
    result: List[str] = []
    for item in lst:
        key = item.lower().strip()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


# ---------------------------------------------------------------------------
# Date normalization helpers (FIX 4)
# ---------------------------------------------------------------------------

_MONTH_ABBR = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}

# Map full/abbreviated month names to month numbers (case-insensitive).
_MONTH_NAME_TO_NUM = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

# Matches "Present", "Current", or "Now" (case-insensitive).
_PRESENT_RE = re.compile(r"^(?:present|current|now)$", re.IGNORECASE)

# Matches MM/YYYY (e.g. "07/2024").
_SLASH_DATE_RE = re.compile(r"^(\d{1,2})/(\d{4})$")

# Matches YYYY-MM (e.g. "2024-07").
_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})$")

# Matches "Month YYYY" or "Month. YYYY" (e.g. "July 2024", "Aug. 2023").
_MONTH_YEAR_RE = re.compile(
    r"^(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\.?\s*,?\s*(\d{4})$",
    re.IGNORECASE,
)


def _normalize_date_token(token: str) -> str:
    """Normalize a single date token (one side of a range) to 'Mon YYYY' or 'Present'.

    Handles:
      "07/2024"   → "Jul 2024"
      "2024-07"   → "Jul 2024"
      "July 2024" → "Jul 2024"
      "Aug. 2023" → "Aug 2023"
      "Present"   → "Present"
      "Current"   → "Present"
      Anything else is returned as-is.
    """
    t = token.strip()
    if not t:
        return t

    if _PRESENT_RE.match(t):
        return "Present"

    m = _SLASH_DATE_RE.match(t)
    if m:
        month_num = int(m.group(1))
        year = m.group(2)
        if 1 <= month_num <= 12:
            return f"{_MONTH_ABBR[month_num]} {year}"
        return t

    m = _ISO_DATE_RE.match(t)
    if m:
        year = m.group(1)
        month_num = int(m.group(2))
        if 1 <= month_num <= 12:
            return f"{_MONTH_ABBR[month_num]} {year}"
        return t

    m = _MONTH_YEAR_RE.match(t)
    if m:
        month_key = m.group(1).lower().rstrip(".")
        year = m.group(2)
        month_num = _MONTH_NAME_TO_NUM.get(month_key)
        if month_num:
            return f"{_MONTH_ABBR[month_num]} {year}"
        return t

    return t


def _parse_dates(date_str: str) -> Tuple[str, str]:
    """Split 'Jan 2022 – Present' or 'July 2024 -- Present' into (start, end).

    After splitting, each token is normalized to abbreviated month + year format:
      "07/2024 – Present"  → ("Jul 2024", "Present")
      "2024-07 – 2025-01"  → ("Jul 2024", "Jan 2025")
      "July 2024 – Present" → ("Jul 2024", "Present")
      "Jan 2022 – Present"  → ("Jan 2022", "Present")   # already correct
    """
    for sep in (" – ", " — ", " -- ", " - ", "–", "—", "--"):
        if sep in date_str:
            parts = date_str.split(sep, 1)
            start = _normalize_date_token(parts[0].strip())
            end = _normalize_date_token(parts[1].strip())
            return start, end
    # Single date (no separator) — normalize and return with empty end.
    return _normalize_date_token(date_str.strip()), ""


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
