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
from typing import Optional

from resume_types import Bullet, Profile, Project, Role
from text_utils import extract_metrics, extract_tools, score_confidence
from parsers.normalizer import _dedupe, _parse_dates


# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------

# Allow an optional period after month abbreviations (e.g. "Aug. 2023") so the
# full range "Aug. 2023 – July 2024" matches as one group (regression for #102:
# previously the regex matched only "July 2024" and the leftover " – July 2024"
# leaked into the company line / following title).
_DATE_PATTERN = re.compile(
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\.?[\s,]*\d{2,4}"
    r"(?:\s*[–\-]\s*(?:\d{2,4}|[Pp]resent|[Cc]urrent|[Nn]ow|"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\.?[\s,]*\d{2,4}))?|"
    r"Q[1-4][\s,]*\d{2,4}"
    r"(?:\s*[–\-]\s*(?:\d{2,4}|[Pp]resent|[Cc]urrent|[Nn]ow))?|"
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


# "City, ST" or "City, Country" trailing location.  Matches the Jake template
# 2-line role header ("Company Name Dallas, TX") where there's no double-space
# separator between company and location.
_TRAILING_LOCATION_RE = re.compile(
    r"^(?P<company>.+?)\s+(?P<loc>[A-Z][A-Za-z .'\-]+,\s*[A-Z][A-Za-z .]{1,30})\s*$"
)


def _split_company_location(s: str) -> tuple[str, str]:
    """Split 'ExponentHR Dallas, TX' into ('ExponentHR', 'Dallas, TX').

    Strategy:
      1. Prefer double-space separator if present.
      2. Else look for a 'City, ST' / 'City, Country' suffix.
      3. Else treat the whole line as company with empty location.
    """
    if "  " in s:
        parts = re.split(r"\s{2,}", s.strip(), maxsplit=1)
        return parts[0].strip(), (parts[1].strip() if len(parts) > 1 else "")
    m = _TRAILING_LOCATION_RE.match(s.strip())
    if m:
        return m.group("company").strip(), m.group("loc").strip()
    return s.strip(), ""


# Project header line:  "Name | Tech1, Tech2, Tech3  Year(s)"
# Examples from Jake template:
#   "Real-Time Fraud Detection Pipeline | PySpark, Kafka, ... 2026"
#   "JobScout – Automated Data Integration Platform | Python, FastAPI ... 2025"
_PROJECT_HEADER_RE = re.compile(
    r"^(?P<name>[^|•]+?)\s*\|\s*(?P<tech>[^|]+?)(?:\s+(?P<year>\d{4}(?:\s*[-–]\s*\d{4})?))?\s*$"
)


def _parse_project_header(ln: str) -> Optional[tuple[str, list, str]]:
    """If ln looks like a 'Name | Tech Year' project header, return
    (name, tech_list, year). Else return None."""
    m = _PROJECT_HEADER_RE.match(ln)
    if not m:
        return None
    name = m.group("name").strip()
    tech_raw = m.group("tech").strip()
    year = (m.group("year") or "").strip()
    tech = [t.strip() for t in re.split(r"[,/]", tech_raw) if t.strip()]
    if not name or len(name) < 3:
        return None
    return name, tech, year


# ---------------------------------------------------------------------------
# Core plain-text parser (shared by PDF and DOCX paths)
# ---------------------------------------------------------------------------

def _parse_plain_resume_text(text: str, source: str = "resume") -> Profile:
    """
    Parse plain text extracted from PDF or DOCX.
    Uses section-header detection + date-pattern heuristics to identify roles.
    Supports 1-line (Title  Company  Date), 2-line (Title+Company / Date),
    and 3-line (Title / Company / Date) role headers via 2-step lookahead.

    Section anchoring (#101): the parser starts in 'preamble' and ignores any
    title-shaped lines (the candidate's name etc.) until it sees a known
    section header \u2014 so the name above the 'Experience' heading is never
    parsed as a role title.

    Disordered-text fallback: pdfminer-style column extraction can pool all
    the date ranges at the top of the file and interleave bullets out of
    order with project headers.  When we encounter a date-only line in the
    experience section with no role context, we stash it in `orphan_dates`
    and pair it positionally with the next role header we see that lacks
    explicit dates.  Bullets that arrive before any role exists are dropped
    silently (preferred over misattribution).
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
    # #101 fix: start in 'preamble' so the candidate-name line at the top of
    # the resume does not get treated as the title of an implicit first role.
    section: Optional[str] = "preamble"
    current_role: Optional[Role] = None
    # Pool of date ranges seen before any role header (pdfminer column order).
    orphan_dates: list[tuple[str, str]] = []

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

        # In the preamble (before the first section header) we ignore
        # everything \u2014 the candidate's name, contact line, summary blurb etc.
        # Exception: pdfminer column-extracted text often pools the date
        # ranges on the first page above the section headers; we stash any
        # bare date-range line for positional pairing with the first roles
        # we encounter in the experience section.
        if section is None or section == "preamble":
            dm = _DATE_PATTERN.search(s)
            if dm and dm.group(0).strip() == s.strip():
                start_o, end_o = _parse_dates(dm.group(0))
                orphan_dates.append((start_o, end_o))
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
                company = ""
                # If the line is *only* a date range with nothing in front,
                # treat it as an orphan date for positional pairing later
                # (pdfminer column-order extraction puts dates on their own
                # lines — fix for #102 disordered case).
                if not pre:
                    start_o, end_o = _parse_dates(dm.group(0))
                    orphan_dates.append((start_o, end_o))
                    continue
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
                    company, location = _split_company_location(next1)
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
                company, location = _split_company_location(next1)
                d = _DATE_PATTERN.search(next2)
                start, end = _parse_dates(d.group(0)) if d else ("", "")
                current_role = Role(title=title, company=company, start=start, end=end, location=location)
                profile.experience.append(current_role)
                i += 2
                continue

            # Fixture-B path: title-only line, no date here / n1 / n2, next1
            # looks like company (and optional location).  Pair positionally
            # with the next orphan date if we have one stashed.
            if (_like_title_line(s) and next1 and not _is_bullet_line(next1)
                    and not _detect_section(next1)
                    and not _DATE_PATTERN.search(s)):
                # Check next1 looks like a company line (no bullet, no date).
                if not _DATE_PATTERN.search(next1):
                    company, location = _split_company_location(next1)
                    # If location is empty and the line after next is a bare
                    # location like 'Dallas, TX', consume it.
                    consumed = 1
                    next2_raw = lines[i + 1] if i + 1 < n else ""
                    if (not location and next2_raw
                            and not _is_bullet_line(next2_raw)
                            and not _detect_section(next2_raw)
                            and not _DATE_PATTERN.search(next2_raw)
                            and re.match(r"^[A-Z][A-Za-z .'\-]+,\s*[A-Z][A-Za-z .]{1,30}$", next2_raw.strip())):
                        location = next2_raw.strip()
                        consumed = 2
                    start, end = ("", "")
                    if orphan_dates:
                        start, end = orphan_dates.pop(0)
                    current_role = Role(
                        title=s.strip(), company=company, start=start, end=end, location=location,
                    )
                    profile.experience.append(current_role)
                    i += consumed
                    continue

            if (s.startswith(("•", "-", "–", "*", "·", "○", "▪"))
                    or re.match(r'^(x|ffi|j)\s+\S', s)):
                txt = re.sub(r'^(?:•|[-–*·○▪]|ffi|x|j)\s+', '', s).strip()
                if len(txt) > 15 and current_role is not None:
                    bullet = Bullet(
                        text=txt,
                        metrics=extract_metrics(txt),
                        tools=extract_tools(txt),
                        evidence_source=source,
                        confidence=score_confidence(txt),
                    )
                    current_role.bullets.append(bullet)
                # else: bullet with no role context — drop silently rather
                # than mis-attribute (fix for #104).

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
            # Project header detection (fix for #103):
            #   1. 'Name | Tech [Year]' pipe-separated header  (Jake template)
            #   2. Short bullet-line that names a project (legacy format,
            #      e.g. '- Real-time Risk Analytics')
            # Long bullet lines are treated as project bullets, never names.
            is_bullet = (s.startswith(("•", "-", "–", "*", "·", "○", "▪"))
                         or bool(re.match(r'^x\s+\S', s)))
            header = None if is_bullet else _parse_project_header(s)
            if header is not None:
                name, tech, year = header
                proj = Project(name=name, tech=tech, date=year)
                profile.projects.append(proj)
                continue

            if is_bullet:
                txt = re.sub(r'^(?:•|[-–*·○▪]|ffi|x|j)\s+', '', s).strip()
                # Short bullet lines (no terminal punctuation, ≤ 60 chars) are
                # treated as project names — the legacy '- Project Name' form.
                # Longer bullet lines (or ones containing a period) are bullets
                # belonging to the most recent project.
                looks_like_name = (
                    txt and len(txt) <= 60
                    and not txt.endswith((".", "%"))
                    and not re.match(r"^(Built|Implemented|Designed|Architected|Developed|Created|Engineered|Migrated|Reengineered|Led|Managed|Reduced|Improved)\b", txt)
                )
                if looks_like_name:
                    proj = Project(name=txt, tech=extract_tools(txt))
                    profile.projects.append(proj)
                elif txt and len(txt) > 10 and profile.projects:
                    bul = Bullet(
                        text=txt, metrics=extract_metrics(txt),
                        tools=extract_tools(txt), evidence_source=source,
                        confidence=score_confidence(txt),
                    )
                    profile.projects[-1].bullets.append(bul)
                continue

            # Non-bullet, non-pipe line in projects section.  Bare year
            # lines (e.g. '2026' on its own line in column-extracted text)
            # are skipped.  Other plain text is treated as a wrap-continuation
            # of the previous bullet (Jake template wraps long bullets).
            clean_s = s.strip()
            if not clean_s or re.fullmatch(r"\d{4}(?:\s*[-–]\s*\d{4})?", clean_s):
                continue
            if (profile.projects and profile.projects[-1].bullets
                    and len(clean_s) > 10):
                last_bul = profile.projects[-1].bullets[-1]
                last_bul.text = (last_bul.text + " " + clean_s).strip()
                # Re-extract metrics/tools from the merged text.
                last_bul.metrics = extract_metrics(last_bul.text)
                last_bul.tools = extract_tools(last_bul.text)

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
