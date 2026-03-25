"""
plain_parser.py
Parse plain text extracted from PDF, DOCX, or free-form blobs into a canonical Profile.

Used by:
  - pdf_extractor.py (after extracting text from PDF bytes)
  - docx_extractor.py (after extracting text from DOCX bytes)
  - __init__.py directly as parse_blob() and parse_linkedin()
"""
from __future__ import annotations

import re
from typing import List, Optional

from resume_types import Bullet, Profile, Project, Role
from text_utils import extract_metrics, extract_tools, score_confidence
from parsers.normalizer import _dedupe, _parse_dates


# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------

_DATE_PATTERN = re.compile(
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?|Q[1-4])[\s,]*\d{2,4}"
    r"(?:\s*[–\-]\s*(?:\d{2,4}|[Pp]resent|[Cc]urrent|[Nn]ow|"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)[\s,]*\d{2,4}))?|"
    r"\d{4}\s*[-–]\s*(?:\d{4}|[Pp]resent|[Cc]urrent|[Nn]ow)",
    re.IGNORECASE,
)

_SECTION_HEADERS = {
    "experience": ["experience", "work experience", "employment", "work history", "professional experience"],
    "education": ["education", "academic", "qualifications"],
    "skills": ["skills", "technical skills", "technologies", "core competencies"],
    "projects": ["projects", "personal projects", "key projects", "technical projects"],
    "certifications": ["certifications", "publications", "licenses", "recognition", "awards"],
}


def _detect_section(line: str) -> Optional[str]:
    """Return canonical section name if the line looks like a section header."""
    clean = line.strip().lower().rstrip(":").strip()
    for sec, aliases in _SECTION_HEADERS.items():
        if clean in aliases:
            return sec
    if len(clean) < 50 and sum(c.isalpha() or c == " " for c in clean) / max(len(clean), 1) > 0.85:
        for sec, aliases in _SECTION_HEADERS.items():
            for alias in aliases:
                if alias in clean:
                    return sec
    return None


def _is_bullet_line(ln: str) -> bool:
    """Return True if ln looks like a bullet-list item (any common prefix)."""
    return ln.startswith(("•", "-", "–", "*", "·", "○", "▪")) or bool(re.match(r'^(x|ffi|j)\s+\S', ln))


def _like_title_line(ln: str) -> bool:
    """Return True if ln could be a role-title line (short, starts uppercase, no bullet)."""
    return (
        bool(ln) and ln[0:1].isupper()
        and len(ln.split()) <= 8 and len(ln) <= 80
        and not re.match(r'^(x|ffi|j)\s+\S', ln)
        and not ln.startswith(("•", "-", "–", "*", "·", "○", "▪"))
    )


# ---------------------------------------------------------------------------
# Core plain-text parser (shared by PDF and DOCX paths)
# ---------------------------------------------------------------------------

def _parse_plain_resume_text(text: str, source: str = "resume") -> Profile:
    """
    Parse plain text extracted from PDF or DOCX.
    Uses section-header detection + date-pattern heuristics to identify roles.
    Supports 1-line (Title  Company  Date), 2-line (Title+Company / Date),
    and 3-line (Title / Company / Date) role headers via 2-step lookahead.
    """
    profile = Profile()
    _months_alt = (r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
                   r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
                   r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?|Present|Current|Now")
    text = re.sub(r"(\d{4})\s+t\s+(" + _months_alt + r")",
                  lambda m: m.group(1) + " \u2013 " + m.group(2),
                  text, flags=re.IGNORECASE)
    text = re.sub(r'(?<!\d)(\d{2,3}) (\d)(?!\d)', r'\1\2', text)
    lines = [line.strip() for line in text.splitlines()]
    n = len(lines)
    section = "experience"
    current_role: Optional[Role] = None

    i = 0
    while i < n:
        s = lines[i]
        i += 1

        if not s:
            continue

        detected = _detect_section(s)
        if detected:
            section = detected
            current_role = None
            continue

        if section == "experience":
            next1 = lines[i] if i < n else ""
            next2 = lines[i + 1] if i + 1 < n else ""
            date_here = _DATE_PATTERN.search(s)
            date_n1 = _DATE_PATTERN.search(next1) if next1 else None
            date_n2 = _DATE_PATTERN.search(next2) if next2 else None

            if date_here:
                dm = date_here
                pre = s[:dm.start()].strip(" |·–—-")
                location = ""
                colon_m = re.match(r'^(.+?)\s*:\s*(.+)$', pre)
                if colon_m:
                    title = colon_m.group(1).strip()
                    rest = colon_m.group(2).strip()
                    comma_m = re.match(r'^([^,]+?)\s*,\s*(.+)$', rest)
                    if comma_m:
                        company = comma_m.group(1).strip()
                        location = comma_m.group(2).strip()
                    else:
                        company = rest
                else:
                    parts = re.split(r"\s{2,}|\s*[|·–]\s*", pre)
                    title = parts[0].strip() if parts else pre
                    company = parts[1].strip() if len(parts) > 1 else ""
                start, end = _parse_dates(dm.group(0))
                if (not company and next1
                        and not _detect_section(next1)
                        and not _DATE_PATTERN.search(next1)
                        and not _is_bullet_line(next1)):
                    loc_parts = re.split(r"\s{2,}", next1.strip())
                    company = loc_parts[0].strip()
                    location = loc_parts[1].strip() if len(loc_parts) > 1 else ""
                    i += 1
                current_role = Role(title=title, company=company, start=start, end=end, location=location)
                profile.experience.append(current_role)
                continue

            if date_n1 and _like_title_line(s):
                _colon_m = re.match(r'^(.+?)\s*:\s*(.+)$', s)
                if _colon_m:
                    title = _colon_m.group(1).strip()
                    _rest = _colon_m.group(2).strip()
                    _comma_m = re.match(r'^([^,]+?)\s*,\s*(.+)$', _rest)
                    if _comma_m:
                        company = _comma_m.group(1).strip()
                        location = _comma_m.group(2).strip()
                    else:
                        company = _rest
                        location = ""
                else:
                    parts = re.split(r"\s{2,}|\s*[|·–]\s*", s)
                    title = parts[0].strip()
                    company = parts[1].strip() if len(parts) > 1 else ""
                    location = ""
                d = _DATE_PATTERN.search(next1)
                start, end = _parse_dates(d.group(0)) if d else ("", "")
                current_role = Role(title=title, company=company, start=start, end=end, location=location)
                profile.experience.append(current_role)
                i += 1
                continue

            if date_n2 and next1 and not _detect_section(next1) and _like_title_line(s) and _like_title_line(next1):
                title = s.strip()
                company = next1.strip()
                d = _DATE_PATTERN.search(next2)
                start, end = _parse_dates(d.group(0)) if d else ("", "")
                current_role = Role(title=title, company=company, start=start, end=end, location="")
                profile.experience.append(current_role)
                i += 2
                continue

            if current_role and (s.startswith(("•", "-", "–", "*", "·", "○", "▪"))
                                  or re.match(r'^(x|ffi|j)\s+\S', s)):
                txt = re.sub(r'^(?:•|[-–*·○▪]|ffi|x|j)\s+', '', s).strip()
                if len(txt) > 15:
                    bullet = Bullet(
                        text=txt,
                        metrics=extract_metrics(txt),
                        tools=extract_tools(txt),
                        evidence_source=source,
                        confidence=score_confidence(txt),
                    )
                    current_role.bullets.append(bullet)

        elif section == "education":
            if not s.startswith(("•", "-")):
                date_m = _DATE_PATTERN.search(s)
                is_degree = any(kw in s.lower() for kw in ("master", "bachelor", "phd", "b.s", "m.s", "b.e", "m.e", "mba", "doctor", "associate"))
                is_inst = any(kw in s.lower() for kw in ("university", "college", "institute", "school", "tech", "polytechnic"))
                if date_m and not is_inst and profile.education:
                    profile.education[-1]["dates"] = s
                elif is_degree and profile.education:
                    if not profile.education[-1]["degree"]:
                        profile.education[-1]["degree"] = s
                    else:
                        profile.education.append({"institution": s, "degree": "", "dates": "", "location": ""})
                elif is_inst or date_m:
                    profile.education.append({"institution": s, "degree": "", "dates": "", "location": ""})

        elif section == "skills":
            for sk in re.split(r"[,;]", s):
                sk = sk.strip(" -*•·|")
                colon_m = re.match(r"^[A-Za-z /&]+:\s*(.+)$", sk)
                if colon_m:
                    for item in re.split(r"[,;/\s]+", colon_m.group(1)):
                        item = item.strip()
                        if item and len(item) > 1:
                            profile.skills.append(item)
                else:
                    if sk and len(sk) > 1:
                        profile.skills.append(sk)

        elif section == "projects":
            is_proj_header = (s.startswith(("•", "-", "–", "*", "·", "○", "▪"))
                              or re.match(r'^x\s+\S', s))
            clean_s = s.lstrip("•-–*·○▪x ").strip()
            if is_proj_header and len(clean_s) > 3:
                proj = Project(name=clean_s, tech=extract_tools(clean_s))
                profile.projects.append(proj)
            elif profile.projects and clean_s and len(clean_s) > 10:
                last = profile.projects[-1]
                bul = Bullet(text=clean_s, metrics=extract_metrics(clean_s),
                             tools=extract_tools(clean_s), evidence_source=source,
                             confidence=score_confidence(clean_s))
                last.bullets.append(bul)

        elif section == "certifications":
            clean_s = s.strip(" -•*·")
            if clean_s and len(clean_s) > 4:
                profile.certifications.append(clean_s)

    profile.skills = _dedupe(profile.skills)
    return profile


# ---------------------------------------------------------------------------
# Blob parser (free-form work experience text)
# ---------------------------------------------------------------------------

def parse_blob(text: str, source: str = "blob") -> Profile:
    """
    Parse free-form work experience blob.
    Detects role headers like:
        Company: Foo  /  Title: Bar  /  Dates: Jan 2022 -- Present
    and bullet lines starting with - or *.
    """
    profile = Profile()
    current_role: Optional[Role] = None
    lines = text.splitlines()

    role_header_re = re.compile(r"(?:company|employer|org(?:anization)?)[:\s]+(.+)", re.IGNORECASE)
    title_re = re.compile(r"(?:title|position|role)[:\s]+(.+)", re.IGNORECASE)
    date_re = re.compile(r"(?:dates?|period|tenure)[:\s]+(.+?)[\s]*(?:–|-|to)[\s]*(.+)", re.IGNORECASE)

    for line in lines:
        s = line.strip()
        if not s:
            continue

        m = role_header_re.match(s)
        if m:
            current_role = Role(title="", company=m.group(1).strip(), start="", end="", location="")
            profile.experience.append(current_role)
            continue

        m = title_re.match(s)
        if m and current_role:
            current_role.title = m.group(1).strip()
            continue

        m = date_re.match(s)
        if m and current_role:
            current_role.start = m.group(1).strip()
            current_role.end = m.group(2).strip()
            continue

        if (s.startswith("- ") or s.startswith("* ")) and current_role:
            txt = s[2:].strip()
            bullet = Bullet(
                text=txt,
                metrics=extract_metrics(txt),
                tools=extract_tools(txt),
                evidence_source=source,
                confidence=score_confidence(txt),
            )
            current_role.bullets.append(bullet)

    return profile


def parse_linkedin(text: str) -> Profile:
    """
    Parse LinkedIn PDF export (pasted as plain text).
    LinkedIn exports have inconsistent formatting; this is a best-effort parser.
    """
    return parse_blob(text, source="linkedin_pdf")
