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
from text_utils import (
    extract_metrics,
    extract_tools,
    score_confidence,
    split_top_level,
)
from parsers.normalizer import _dedupe, _parse_dates


# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------

# Allow an optional period after month abbreviations (e.g. "Aug. 2023") so the
# full range "Aug. 2023 – July 2024" matches as one group (regression for #102:
# previously the regex matched only "July 2024" and the leftover " – July 2024"
# leaked into the company line / following title).
# Fix 5: separator alternation includes "to", "thru", "through" in addition to
# dash variants, so "Jan 2021 to Dec 2022" (LinkedIn / DOCX exports) matches.
_SEP = r"(?:\s*(?:[–\-]|to|thru|through)\s*)"
_DATE_PATTERN = re.compile(
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\.?[\s,]*\d{2,4}"
    r"(?:" + _SEP + r"(?:\d{2,4}|[Pp]resent|[Cc]urrent|[Nn]ow|"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\.?[\s,]*\d{2,4}))?|"
    r"Q[1-4][\s,]*\d{2,4}"
    r"(?:" + _SEP + r"(?:\d{2,4}|[Pp]resent|[Cc]urrent|[Nn]ow))?|"
    r"\d{4}\s*(?:[–\-]|to|thru|through)\s*(?:\d{4}|[Pp]resent|[Cc]urrent|[Nn]ow)|"
    # Enhancement #2: MM/YYYY slash format (LinkedIn, Word exports)
    r"\d{1,2}/\d{4}(?:" + _SEP + r"(?:\d{1,2}/\d{4}|[Pp]resent|[Cc]urrent|[Nn]ow))?|"
    # Enhancement #2: ISO YYYY-MM format
    r"\d{4}-\d{2}(?:" + _SEP + r"(?:\d{4}-\d{2}|[Pp]resent|[Cc]urrent|[Nn]ow))?",
    re.IGNORECASE,
)

# Fix 6 + Enhancement #5: extended aliases cover common ATS section header variants seen in
# LinkedIn exports, Word templates, and non-Jake LaTeX styles.
_SECTION_HEADERS = {
    "summary": [
        "summary", "profile", "objective", "professional summary",
        "summary of qualifications", "about me", "career objective",
    ],
    "experience": [
        "experience", "work experience", "employment", "work history",
        "professional experience", "employment history",
    ],
    "education": ["education", "academic", "qualifications"],
    "skills": ["skills", "technical skills", "technologies", "core competencies"],
    "projects": [
        "projects", "personal projects", "key projects", "technical projects",
        "side projects", "open source",
    ],
    "certifications": [
        "certifications", "publications", "licenses", "recognition", "awards",
        "achievements", "honors",
    ],
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


# Enhancement #4: contact-info regex for preamble scanning
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.\w{2,}")
_PHONE_RE = re.compile(r"[\+\(]?[\d\s\-\(\)]{7,15}\d")
_URL_RE   = re.compile(r"https?://\S+|linkedin\.com/\S+|github\.com/\S+", re.IGNORECASE)

# Detects GPA within a text fragment.
_GPA_RE = re.compile(
    r"(?<![A-Za-z])(?:C)?GPA[:\s]+(?P<gpa>[\d.]+(?:/[\d.]+)?)",
    re.IGNORECASE,
)
# Matches a line that starts with a month name — these are bare date ranges,
# not institution names, so the one-liner should not match them.
_STARTS_WITH_MONTH_RE = re.compile(
    r"^(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\b",
    re.IGNORECASE,
)


# Degree-first detection helpers — used in _parse_education_oneliner.
_DEGREE_FIRST_RE = re.compile(
    r"^(?:B\.?(?:Tech|Sc|A|S|E|Ed|Eng)?\.?|M\.?(?:Tech|Sc|S|A|E|Ed|Eng|B|Phil)?\.?|"
    r"Ph\.?D\.?|Dr\.?|MBA|LLB|BCA|MCA|Bachelor|Master|Doctor|Associate|Diploma|"
    r"Doctor\s+of)\b",
    re.IGNORECASE,
)
_INST_KEYWORD_RE = re.compile(
    r"\b(?:University|College|Institute|School|Technology|Tech|Polytechnic|Academy|"
    r"MIT|IIT|IIM|NIT|BITS|UCLA|NYU|CMU|LSE|ETH)\b",
    re.IGNORECASE,
)

# Strategy 0: year-first normalization (moderncv, some Word templates).
# "2014–2018  B.Sc. Mathematics  University of Edinburgh" — detect the
# date prefix, strip it, continue parsing the remainder as the real content.
_YEAR_FIRST_RE = re.compile(
    r"^(?P<dates>\d{4}\s*[–\-]\s*(?:\d{4}|Present|Current|Now))\s{2,}(?P<rest>.+)",
    re.IGNORECASE,
)

# Bare month-name date lines (e.g. "Jan 2022 – Dec 2023") must fall through.
# Guard: only reject when month word is immediately followed by a digit/comma/space+digit
# so "May University" and "March College" are NOT rejected.
_BARE_DATE_RE = re.compile(
    r"^(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)[.\s,]+\d{2,4}",
    re.IGNORECASE,
)


def _parse_education_oneliner(line: str):  # noqa: C901  (complexity is intentional)
    """Try to parse a condensed single-line education entry.

    Handles formats like:
      "Institution — Degree | GPA: X.X | Jan YYYY – Dec YYYY"   (pipe/em-dash)
      "Institution | Degree | Dates"                              (all-pipe)
      "Institution  Degree  Dates"                               (double-space)
      "Degree, Institution, Year"                                (comma-separated)
      "Degree | Institution | Dates"                             (degree-first)

    Returns a dict with institution/degree/dates/location on match,
    or None to signal fallthrough to the existing multi-line heuristic.
    """
    s = line.strip()
    if not s:
        return None

    # Strategy 0: year-first normalization (moderncv, some Word templates).
    # "2014–2018  B.Sc. Mathematics  University of Edinburgh" — detect the
    # date prefix, strip it, continue parsing the remainder as the real content.
    yf_m = _YEAR_FIRST_RE.match(s)
    extracted_year_first_dates: str = ""
    if yf_m:
        extracted_year_first_dates = yf_m.group("dates").strip()
        s = yf_m.group("rest").strip()
        # Re-check guards after stripping the date prefix.
        if not s or not s[0].isupper():
            return None
    elif s[0].isdigit():
        # Bare date line — fall through to the multi-line heuristic.
        return None
    elif not s[0].isupper():
        # Non-uppercase, non-digit first char: not an institution or degree line.
        return None

    # Bare month-name date lines (e.g. "Jan 2022 – Dec 2023") must fall through.
    # Guard: only reject when month word is immediately followed by a digit/comma/space+digit
    # so "May University" and "March College" are NOT rejected.
    if _BARE_DATE_RE.match(s):
        return None

    # --- Strategy 1: pipe (|) or em-dash (—) field separator ---
    # Split on all pipes and em-dashes simultaneously (preserves backward compat
    # for lines that mix both, e.g. "Missouri S&T — M.S. ... | GPA | Dates").
    if re.search(r"[|—]", s):
        raw_parts = re.split(r"\s*[|—]\s*", s)
    else:
        # --- Strategy 2: double-space separator ---
        raw_parts = re.split(r"\s{2,}", s)

    if len(raw_parts) < 2:
        # --- Strategy 3: comma-delimited fallback (AltaCV, international formats) ---
        comma_parts = [p.strip() for p in s.split(",") if p.strip()]
        _has_deg = any(_DEGREE_FIRST_RE.search(p) for p in comma_parts)
        _has_inst = any(_INST_KEYWORD_RE.search(p) for p in comma_parts)
        if 2 <= len(comma_parts) <= 5 and (_has_deg or _has_inst):
            raw_parts = comma_parts
        else:
            return None

    # --- Degree-first detection: swap parts[0] and parts[1] if needed ---
    # Applies to all strategies after splitting.
    if (_DEGREE_FIRST_RE.match(raw_parts[0].strip())
            and len(raw_parts) >= 2
            and not _INST_KEYWORD_RE.search(raw_parts[0])):
        # First token looks like a degree; find the best institution candidate.
        # Prefer a token that explicitly contains an institution keyword; otherwise
        # take the first non-date, non-GPA, non-digit token after index 0.
        best_inst_idx = None
        for idx in range(1, len(raw_parts)):
            p = raw_parts[idx].strip()
            if _INST_KEYWORD_RE.search(p):
                best_inst_idx = idx
                break
        if best_inst_idx is None:
            # No clear institution keyword; heuristic: first non-numeric uppercase token.
            for idx in range(1, len(raw_parts)):
                p = raw_parts[idx].strip()
                if not _DATE_PATTERN.search(p) and not _GPA_RE.search(p) and p and p[0].isupper():
                    best_inst_idx = idx
                    break
        if best_inst_idx is not None:
            new_parts = list(raw_parts)
            new_parts[0], new_parts[best_inst_idx] = new_parts[best_inst_idx], new_parts[0]
            raw_parts = new_parts

    inst = raw_parts[0].strip().rstrip("–—-,")
    if not inst or not inst[0].isupper() or _BARE_DATE_RE.match(inst):
        return None

    # Fix 2: hyphen-minus used as institution–degree separator (e.g. "May University - B.S. Biology").
    # If `inst` contains " - " and the right-hand side starts with a degree token, split further.
    _hyph_match = re.search(r'\s+-\s+', inst)
    if _hyph_match:
        _right = inst[_hyph_match.end():]
        if _DEGREE_FIRST_RE.search(_right):
            inst = inst[:_hyph_match.start()].strip()
            # Prepend the extracted degree fragment to raw_parts so the classifier sees it.
            raw_parts = [raw_parts[0][:_hyph_match.start()].strip()] + [_right] + list(raw_parts[1:])

    # --- Classify remaining tokens directly (avoid pipe-artifact in rejoined string) ---
    mid_parts = [p.strip() for p in raw_parts[1:] if p.strip()]
    dates: str = extracted_year_first_dates
    gpa: str = ""
    deg_parts: list = []

    for p in mid_parts:
        # Check GPA first (before date) so "GPA: 4.0/4.0" is not consumed by date.
        gm = _GPA_RE.search(p)
        if gm and not gpa:
            gpa = gm.group("gpa")
            # Keep any non-GPA fragment of this token.
            leftover = (p[:gm.start()] + p[gm.end():]).strip(" |–—-")
            if leftover and not _DATE_PATTERN.search(leftover):
                deg_parts.append(leftover)
            continue
        dm = _DATE_PATTERN.search(p)
        if dm and not dates:
            # Extract only the matched span, not trailing junk.
            dates = dm.group(0).strip()
            # If there is content before the date in this token, it belongs to degree.
            pre_date = p[:dm.start()].strip(" |–—-")
            if pre_date:
                deg_parts.append(pre_date)
            continue
        # Fix 1: bare 4-digit year not matched by _DATE_PATTERN (e.g. "2018").
        if not dates and re.fullmatch(r'\d{4}', p):
            dates = p
            continue
        deg_parts.append(p)

    deg = " ".join(deg_parts).strip(" |–—-")
    if not deg:
        return None

    if gpa:
        deg = f"{deg} (GPA: {gpa})"

    return {"institution": inst, "degree": deg, "dates": dates, "location": ""}


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


# Back-compat alias for any caller / test that imports the previous name.
# The implementation now lives in text_utils.split_top_level so the same fix
# applies to profile_extractor.py and latex_parser.py call sites.
_split_skills_respect_parens = split_top_level


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
    # BUT: if the input has no recognisable section header anywhere (e.g. a
    # bare role snippet fed to the parser by a unit test or a paste from a
    # job-portal text box), fall back to the legacy default of starting in
    # 'experience' so something gets parsed instead of nothing.
    _text_lower = text.lower()
    _has_any_section = any(
        alias in _text_lower
        for aliases in _SECTION_HEADERS.values()
        for alias in aliases
    )
    section: Optional[str] = "preamble" if _has_any_section else "experience"
    current_role: Optional[Role] = None
    # Pool of date ranges seen before any role header (pdfminer column order).
    orphan_dates: list[tuple[str, str]] = []
    # Pool of bullets that arrive before any project header (pdfminer column
    # order puts right-column dates/years at the same y-level as a bullet that
    # visually belongs to the next project header).  Attached to the next
    # project that is parsed.  Fix for #115.
    orphan_project_bullets: list[Bullet] = []

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

        # In the preamble (before the first section header) we extract contact
        # info and stash orphan date ranges for positional pairing with roles.
        # Enhancement #4: scan name, email, phone, linkedin, github from preamble.
        if section is None or section == "preamble":
            dm = _DATE_PATTERN.search(s)
            if dm and dm.group(0).strip() == s.strip():
                start_o, end_o = _parse_dates(dm.group(0))
                orphan_dates.append((start_o, end_o))
                continue
            email_m = _EMAIL_RE.search(s)
            if email_m and not profile.contact.get("email"):
                profile.contact["email"] = email_m.group(0)
            phone_m = _PHONE_RE.search(s)
            if phone_m and not profile.contact.get("phone"):
                profile.contact["phone"] = phone_m.group(0).strip()
            for url in _URL_RE.findall(s):
                if "linkedin" in url.lower() and not profile.contact.get("linkedin"):
                    profile.contact["linkedin"] = url
                elif "github" in url.lower() and not profile.contact.get("github"):
                    profile.contact["github"] = url
            # First short all-alpha line with no contact data \u2192 candidate name
            if (not profile.contact.get("name") and not email_m and not phone_m
                    and not _URL_RE.search(s) and not dm
                    and len(s.split()) <= 5 and s and s[0].isupper()):
                profile.contact["name"] = s
            continue

        # Enhancement #5: accumulate summary/profile/objective text
        if section == "summary":
            if profile.summary:
                profile.summary += " " + s
            else:
                profile.summary = s
            continue

        if section == "experience":
            # Enhancement #7: skip subheaders like "Responsibilities:", "Key Achievements:"
            if current_role is not None and s.rstrip().endswith(":") and len(s.split()) <= 5:
                continue

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
            elif (current_role is not None and current_role.bullets
                  and not date_here and len(s) > 10
                  and s and s[0].islower()):
                # Enhancement #8: wrap-continuation — lowercase line with no date/section
                # prefix is a wrapped tail of the previous bullet (common in PDF extracts).
                last = current_role.bullets[-1]
                last.text = (last.text + " " + s).strip()
                last.metrics = extract_metrics(last.text)
                last.tools = extract_tools(last.text)

        elif section == "education":
            if not s.startswith(("•", "-")):
                # Enhancement #9 (Issue #129): try single-line parser first.
                # Handles "Institution — Degree | GPA | Dates" condensed format
                # common in LinkedIn exports and Word templates.
                oneliner = _parse_education_oneliner(s)
                if oneliner:
                    def _norm_inst(s: str) -> str:
                        return s.strip().lower()
                    # Merge into the previous stub if it has the same institution and
                    # no degree yet.  Drop the 'not dates' requirement so a stub that
                    # already has dates can still accept a missing degree.
                    if (profile.education
                            and not profile.education[-1]["degree"]
                            and _norm_inst(profile.education[-1]["institution"]) == _norm_inst(oneliner["institution"])):
                        # Copy only keys that are currently empty to avoid overwriting good data.
                        for k, v in oneliner.items():
                            if not profile.education[-1].get(k):
                                profile.education[-1][k] = v
                    else:
                        profile.education.append(oneliner)
                else:
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
            # #114: split on commas/semicolons that are NOT inside parens so
            # entries like 'Azure (AKS, DevOps, Data Factory)' stay together.
            for sk in _split_skills_respect_parens(s):
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
                # Attach bullets that arrived before this header in
                # column-ordered pdfminer output (fix for #115).
                proj.bullets.extend(orphan_project_bullets)
                orphan_project_bullets.clear()
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
                    proj.bullets.extend(orphan_project_bullets)
                    orphan_project_bullets.clear()
                    profile.projects.append(proj)
                elif txt and len(txt) > 10:
                    bul = Bullet(
                        text=txt, metrics=extract_metrics(txt),
                        tools=extract_tools(txt), evidence_source=source,
                        confidence=score_confidence(txt),
                    )
                    if profile.projects:
                        profile.projects[-1].bullets.append(bul)
                    else:
                        # Bullet arrived before any project header — stash it
                        # for the next project (pdfminer column-order, #115).
                        orphan_project_bullets.append(bul)
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
