"""
profile_extractor.py
Parses resume artifacts (markdown, LaTeX, plain blobs, LinkedIn text, PDF, DOCX)
into a canonical profile JSON. PII is never stored — caller passes text at runtime.

Usage:
    python profile_extractor.py --input resume.tex --format latex
    python profile_extractor.py --input resume.pdf --format pdf
    python profile_extractor.py --input resume.docx --format docx
    python profile_extractor.py --input blob.txt --format blob
"""
from __future__ import annotations

import argparse
import json
import re
from typing import List, Optional, Tuple

from resume_types import Bullet, Profile, Project, Role, profile_to_dict
from text_utils import extract_metrics, extract_tools, score_confidence


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


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

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

    # Attach bullets to roles by position in the section text
    _attach_bullets_to_roles(exp_body, profile.experience, source)

    # ---- Projects ----------------------------------------------------------
    proj_body = sections.get("projects", "") or sections.get("personal projects", "")
    current_proj: Optional[Project] = None

    for m in re.finditer(r"\\resumeProjectHeading", proj_body):
        args, _ = _extract_args(proj_body, m.end(), 2)
        if not args:
            continue
        raw_name = _clean_latex(args[0])
        # Split "Name | Tech stack" — template uses $|$ or |
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
        profile.education.append({
            "institution": _clean_latex(args[0]),
            "degree": _clean_latex(args[2]) if len(args) > 2 else "",
            "dates": _clean_latex(args[1]),
            "location": _clean_latex(args[3]) if len(args) > 3 else "",
        })

    # ---- Skills ------------------------------------------------------------
    skills_body = ""
    for key in ("technical skills", "skills", "technologies"):
        if key in sections:
            skills_body = sections[key]
            break
    if skills_body:
        # Extract \textbf{Category}: skill1, skill2 — and also plain comma lists
        for m in re.finditer(r"\\textbf\{([^}]+)\}\{?:?\}?\s*([^\\\n]+)", skills_body):
            vals = m.group(2)
            for sk in re.split(r"[,;]", vals):
                sk = sk.strip(" \\{}$|")
                if sk and len(sk) > 1:
                    profile.skills.append(sk)
        # Also pick up bare skill tokens if skills section is sparse
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


def _parse_dates(date_str: str) -> Tuple[str, str]:
    """Split 'Jan 2022 – Present' or 'July 2024 -- Present' into (start, end)."""
    for sep in (" – ", " — ", " -- ", " - ", "–", "—", "--"):
        if sep in date_str:
            parts = date_str.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    return date_str.strip(), ""


def _attach_bullets_to_roles(body: str, roles: List[Role], source: str) -> None:
    """Find all \\resumeItem{} in body and attach them to the correct role by position."""
    if not roles:
        return
    # Get the position of each role's \\resumeSubheading in the body
    sub_positions: List[int] = [m.start() for m in re.finditer(r"\\resumeSubheading", body)]
    # Get all items with their positions
    for m in re.finditer(r"\\resumeItem", body):
        item_pos = m.start()
        args, _ = _extract_args(body, m.end(), 1)
        if not args:
            continue
        txt = _clean_latex(args[0])
        if not txt:
            continue
        # Find which role this item belongs to (largest sub_position <= item_pos)
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


def _dedupe(lst: List[str]) -> List[str]:
    return list(dict.fromkeys(lst))


# ---------------------------------------------------------------------------
# Blob parser
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


# ---------------------------------------------------------------------------
# Markdown parser
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# LinkedIn parser
# ---------------------------------------------------------------------------

def parse_linkedin(text: str) -> Profile:
    """
    Parse LinkedIn PDF export (pasted as plain text).
    LinkedIn exports have inconsistent formatting; this is a best-effort parser.
    """
    return parse_blob(text, source="linkedin_pdf")


# ---------------------------------------------------------------------------
# PDF text extraction — stdlib fallback (no external deps required)
# ---------------------------------------------------------------------------

def _pdf_read_string(block: str, pos: int) -> tuple:
    """
    Read a PDF literal string starting at pos (which should point at '(').
    Returns (content, new_pos). Handles nested parens and backslash escapes.
    No regex — O(n), no backtracking.
    """
    assert block[pos] == "("
    pos += 1
    depth = 1
    buf: List[str] = []
    while pos < len(block) and depth > 0:
        c = block[pos]
        if c == "\\":
            if pos + 1 < len(block):
                buf.append(c)
                buf.append(block[pos + 1])
                pos += 2
            else:
                pos += 1
        elif c == "(":
            depth += 1
            buf.append(c)
            pos += 1
        elif c == ")":
            depth -= 1
            if depth > 0:
                buf.append(c)
            pos += 1
        else:
            buf.append(c)
            pos += 1
    return "".join(buf), pos


def _pdf_hex_to_text(hex_str: str) -> str:
    """
    Decode a PDF hex string <XXXX> as UTF-16-BE (CIDFont/Word PDFs) or latin-1
    (Type1/OT1 LaTeX PDFs).  Strategy: try UTF-16-BE and keep it only when the
    result is ≥ 75 % ASCII printable (genuine Unicode text).  Otherwise fall
    back to latin-1 byte-by-byte so that glyphs like <5458> → "TX" are
    preserved.  The OT1 map is applied later in the piece-cleaning loop.
    """
    hex_str = re.sub(r"\s+", "", hex_str)
    if len(hex_str) % 2 != 0:
        hex_str += "0"
    try:
        raw = bytes.fromhex(hex_str)
    except ValueError:
        return ""
    # Try UTF-16-BE first — only accept when result is mostly ASCII printable
    # (heuristic: ≥ 75 % of chars in 0x20-0x7E).  A LaTeX Type1 font like
    # <5458> → U+5458 '员' fails this check and correctly falls back to latin-1.
    if len(raw) >= 2 and len(raw) % 2 == 0:
        try:
            text = raw.decode("utf-16-be", errors="strict")
            ascii_printable = sum(1 for c in text if 32 <= ord(c) <= 126)
            if ascii_printable >= len(text) * 0.75:
                return text
        except Exception:
            pass
    # Fallback: latin-1 byte-by-byte (Type1 / OT1 encoding)
    return "".join(chr(b) for b in raw if chr(b).isprintable())


# LaTeX OT1 font encoding — byte values that don't map to their ASCII equivalents.
# Applied after latin-1 decode, before the printable-char filter.
_OT1_MAP: dict = {
    "\x0c": "fi",    # fi ligature
    "\x0d": "fl",    # fl ligature
    "\x0e": "ff",    # ff ligature
    "\x0f": "ffi",   # ffi ligature
    "\x10": "ffl",   # ffl ligature
    "\x7b": "\u2013",  # { → en dash
    "\x7c": "\u2014",  # | → em dash
    "\x95": "\u2022",  # latin-1 bullet (0x95) → •
    # Unicode precomposed ligatures (some PDF ToUnicode CMaps emit these)
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
}


def _apply_ot1(s: str) -> str:
    """Substitute OT1-encoded bytes/ligature chars with readable equivalents."""
    for src, dst in _OT1_MAP.items():
        s = s.replace(src, dst)
    return s


def _extract_pdf_text_stdlib(data: bytes) -> str:
    """
    Stdlib-only PDF text extractor. No regex on unbounded content — avoids
    catastrophic backtracking on large PDFs.

    Handles:
    - FlateDecode (zlib) compressed streams
    - Absolute positioning via Tm matrix (1 0 0 1 x y Tm) — correctly
      reconstructs 2-column layouts by grouping pieces at the same y
    - Literal strings Tj / [(text) kern] TJ with OT1 ligature mapping
    - Hex strings <XXXX> Tj / TJ — UTF-16-BE decode (Word/GDocs PDFs)
    - T*, Td/TD, ' operators for relative line movement
    """
    import zlib

    # Decompress all FlateDecode streams
    raw_streams: List[bytes] = []
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.DOTALL):
        s = m.group(1)
        try:
            raw_streams.append(zlib.decompress(s))
        except Exception:
            raw_streams.append(s)
    if not raw_streams:
        raw_streams = [data]

    # Collect (x, y, text) pieces; we'll group by y to reconstruct visual lines
    pieces: List[Tuple[float, float, str]] = []

    def _parse_tj_array(arr: str) -> str:
        """Extract and join text from the content of a TJ array [ ... ]."""
        parts: List[str] = []
        ap = 0
        an = len(arr)
        while ap < an:
            ac = arr[ap]
            if ac == "(":
                s, ap = _pdf_read_string(arr, ap)
                parts.append(s)
            elif ac == "<" and (ap + 1 >= an or arr[ap + 1] != "<"):
                aend = arr.find(">", ap + 1)
                if aend != -1:
                    parts.append(_pdf_hex_to_text(arr[ap + 1:aend]))
                    ap = aend + 1
                else:
                    ap += 1
            else:
                # Kerning number — large negative value = word space
                num_m = re.match(r"-?\d+(?:\.\d*)?", arr[ap:])
                if num_m:
                    try:
                        kern = float(num_m.group())
                        if kern < -150 and parts:
                            parts.append(" ")
                    except ValueError:
                        pass
                    ap += num_m.end()
                else:
                    ap += 1
        return "".join(parts)

    for raw in raw_streams:
        try:
            txt = raw.decode("latin-1", errors="replace")
        except Exception:
            txt = raw.decode("utf-8", errors="replace")

        for block_m in re.finditer(r"BT(.*?)ET", txt, re.DOTALL):
            block = block_m.group(1)
            n = len(block)
            pos = 0

            # Text state — absolute position from Tm, relative offsets from Td
            tm_x = 0.0
            tm_y = 0.0
            td_x = 0.0
            td_y = 0.0
            leading = 12.0  # default assumed leading for T*

            current: List[str] = []

            def emit(txt_pieces: List[str], cx: float, cy: float) -> None:
                joined = "".join(txt_pieces)
                if joined.strip():
                    pieces.append((cx, cy, joined))

            while pos < n:
                c = block[pos]

                # Skip whitespace
                if c in " \t\r\n":
                    pos += 1
                    continue

                # Tm — absolute text matrix: a b c d x y Tm
                m2 = re.match(
                    r"(-?\d+(?:\.\d*)?)\s+(-?\d+(?:\.\d*)?)\s+"
                    r"(-?\d+(?:\.\d*)?)\s+(-?\d+(?:\.\d*)?)\s+"
                    r"(-?\d+(?:\.\d*)?)\s+(-?\d+(?:\.\d*)?)\s+Tm",
                    block[pos:]
                )
                if m2:
                    if current:
                        emit(current, tm_x + td_x, tm_y + td_y)
                        current = []
                    tm_x = float(m2.group(5))
                    tm_y = float(m2.group(6))
                    td_x = 0.0
                    td_y = 0.0
                    pos += m2.end()
                    continue

                # TL — set leading (for T*)
                m2 = re.match(r"(-?\d+(?:\.\d*)?)\s+TL", block[pos:])
                if m2:
                    try:
                        leading = abs(float(m2.group(1)))
                    except ValueError:
                        pass
                    pos += m2.end()
                    continue

                # Td or TD — relative move
                m2 = re.match(r"(-?\d+(?:\.\d*)?)\s+(-?\d+(?:\.\d*)?)\s+T[dD]", block[pos:])
                if m2:
                    dx = float(m2.group(1))
                    dy = float(m2.group(2))
                    if current and abs(dy) > 0.5:
                        emit(current, tm_x + td_x, tm_y + td_y)
                        current = []
                    td_x += dx
                    td_y += dy
                    pos += m2.end()
                    continue

                # T* — move to next line (y -= leading)
                if block[pos:pos+2] == "T*":
                    if current:
                        emit(current, tm_x + td_x, tm_y + td_y)
                        current = []
                    td_y -= leading
                    pos += 2
                    continue

                # Literal string: (text)
                if c == "(":
                    s, pos = _pdf_read_string(block, pos)
                    j = pos
                    while j < n and block[j] in " \t\r\n":
                        j += 1
                    if j < n:
                        if block[j:j+2] == "Tj" and (j + 2 >= n or not block[j+2].isalpha()):
                            current.append(s)
                            pos = j + 2
                        elif block[j] == "'":
                            if current:
                                emit(current, tm_x + td_x, tm_y + td_y)
                            td_y -= leading
                            current = [s] if s else []
                            pos = j + 1
                        else:
                            pos = j
                    continue

                # Hex string: <hex>
                if c == "<" and (pos + 1 >= n or block[pos + 1] != "<"):
                    end = block.find(">", pos + 1)
                    if end == -1:
                        pos += 1
                        continue
                    hex_content = block[pos + 1:end]
                    pos = end + 1
                    j = pos
                    while j < n and block[j] in " \t\r\n":
                        j += 1
                    if j < n and block[j:j+2] == "Tj" and (j + 2 >= n or not block[j+2].isalpha()):
                        decoded = _pdf_hex_to_text(hex_content)
                        if decoded:
                            current.append(decoded)
                        pos = j + 2
                    continue

                # TJ array: [ ... ] TJ
                if c == "[":
                    depth = 1
                    j = pos + 1
                    while j < n and depth > 0:
                        if block[j] == "[":
                            depth += 1
                            j += 1
                        elif block[j] == "]":
                            depth -= 1
                            j += 1
                        elif block[j] == "(":
                            _, j = _pdf_read_string(block, j)
                        elif block[j] == "<" and (j + 1 >= n or block[j + 1] != "<"):
                            end = block.find(">", j + 1)
                            j = end + 1 if end != -1 else j + 1
                        elif block[j] == "\\":
                            j += 2
                        else:
                            j += 1
                    arr_end = j
                    k = arr_end
                    while k < n and block[k] in " \t\r\n":
                        k += 1
                    if k < n and block[k:k+2] == "TJ" and (k + 2 >= n or not block[k+2].isalpha()):
                        arr_text = _parse_tj_array(block[pos + 1:arr_end - 1])
                        if arr_text:
                            current.append(arr_text)
                        pos = k + 2
                    else:
                        pos = arr_end
                    continue

                # Skip any other token (numbers, font ops, gs, etc.)
                # Stop before PDF delimiters so that a construct like
                # "-0.05 Tc[(TX)] TJ" does not get consumed as one giant token,
                # which would prevent the '[' from being seen as a TJ array.
                m2 = re.match(r"[^\s\[(<]+", block[pos:])
                if m2:
                    pos += m2.end()
                else:
                    pos += 1

            if current:
                emit(current, tm_x + td_x, tm_y + td_y)

    # ----------------------------------------------------------------
    # Reconstruct visual lines: group pieces by y (±3pt tolerance),
    # sort each group left→right by x, join with space.
    # ----------------------------------------------------------------
    def _unescape(s: str) -> str:
        s = (s.replace("\\n", " ").replace("\\r", " ")
              .replace("\\t", " ").replace("\\(", "(")
              .replace("\\)", ")").replace("\\\\", "\\"))
        s = re.sub(r"\\([0-7]{1,3})", lambda m: chr(int(m.group(1), 8) % 128), s)
        return s

    # Clean each piece
    cleaned_pieces: List[Tuple[float, float, str]] = []
    for px, py, ptxt in pieces:
        ptxt = _unescape(ptxt)
        ptxt = _apply_ot1(ptxt)
        ptxt_p = "".join(c for c in ptxt if c.isprintable())
        if not ptxt_p:
            continue
        # Whitespace-only pieces become a single " " sentinel so that the
        # x-gap joining in _group_to_lines can see the visual space that was
        # rendered by the PDF without carrying stray blank content.
        stored = " " if not ptxt_p.strip() else ptxt_p
        cleaned_pieces.append((px, py, stored))

    if not cleaned_pieces:
        return ""

    Y_TOL = 3.0

    # Rough character width estimate (pts) for ~10pt fonts — used to decide
    # whether consecutive pieces on the same line need a word-space between
    # them.  If the x-gap between piece N and piece N+1 is ≤ len(piece_N) *
    # CHAR_W, they are visually adjacent (same word); no extra space is added.
    # This fixes split words ("Mi ssouri" → "Missouri") and split years
    # ("202 4" → "2024") that arise when every glyph run is its own BT block.
    CHAR_W = 4.0  # pt — conservative average for CMR 10 / Computer Modern

    def _group_to_lines(ps: List[Tuple[float, float, str]]) -> List[str]:
        """Group pieces by y (±Y_TOL), sort each group by x, smart-join."""
        if not ps:
            return []
        ps_sorted = sorted(ps, key=lambda p: (-p[1], p[0]))
        result: List[str] = []
        grp: List[Tuple[float, float, str]] = [ps_sorted[0]]
        for px, py, ptxt in ps_sorted[1:]:
            if abs(py - grp[0][1]) <= Y_TOL:
                grp.append((px, py, ptxt))
            else:
                grp.sort(key=lambda p: p[0])
                # Smart join: omit inter-piece space when pieces are adjacent
                parts = [grp[0][2]]
                for k in range(1, len(grp)):
                    prev_x, _, prev_txt = grp[k - 1]
                    cur_x, _, cur_txt = grp[k]
                    gap = cur_x - prev_x
                    adjacent = gap <= len(prev_txt) * CHAR_W * 1.1
                    parts.append(cur_txt if adjacent else " " + cur_txt)
                result.append("".join(parts))
                grp = [(px, py, ptxt)]
        if grp:
            grp.sort(key=lambda p: p[0])
            parts = [grp[0][2]]
            for k in range(1, len(grp)):
                prev_x, _, prev_txt = grp[k - 1]
                cur_x, _, cur_txt = grp[k]
                gap = cur_x - prev_x
                adjacent = gap <= len(prev_txt) * CHAR_W * 1.1
                parts.append(cur_txt if adjacent else " " + cur_txt)
            result.append("".join(parts))
        return result

    # Detect two-column layout by finding the largest gap in the global x
    # distribution.  A sidebar-style 2-column LaTeX resume has all left-column
    # pieces below some x threshold and all right-column pieces above it,
    # producing a clear "desert" in the x histogram (even if only 20-25pt wide).
    col_split_x: Optional[float] = None
    if len(cleaned_pieces) > 4:
        all_xs_g = sorted(p[0] for p in cleaned_pieces)
        max_gap_g = 0.0
        for i in range(1, len(all_xs_g)):
            gap = all_xs_g[i] - all_xs_g[i - 1]
            if gap > max_gap_g:
                max_gap_g = gap
                col_split_x = (all_xs_g[i] + all_xs_g[i - 1]) / 2.0
        if max_gap_g < 18.0:   # no reliable column separator found
            col_split_x = None

    if col_split_x is not None:
        # Two-column layout: process each column independently top-to-bottom,
        # then concatenate (left column first, right column second).
        left_pieces = [(x, y, t) for x, y, t in cleaned_pieces if x < col_split_x]
        right_pieces = [(x, y, t) for x, y, t in cleaned_pieces if x >= col_split_x]
        lines_out = _group_to_lines(left_pieces) + _group_to_lines(right_pieces)
    else:
        lines_out = _group_to_lines(cleaned_pieces)

    # Filter garbage lines
    cleaned: List[str] = []
    for line in lines_out:
        if len(line) < 2:
            continue
        alpha = sum(c.isalpha() for c in line)
        if alpha / len(line) < 0.25 and not re.search(r"\d", line):
            continue
        cleaned.append(line)

    text_out = "\n".join(cleaned)

    # Post-process: fix artefacts from per-glyph BT blocks in LaTeX PDFs.
    # (1) Lone "t" between a 4-digit year and a month/Present = en dash glyph
    #     that survived as chr(0x74) after CID font decode.
    _MONTHS_RE = (r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
                  r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
                  r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?|Present|Current|Now")
    text_out = re.sub(
        r"(\d{4})\s+t\s+(" + _MONTHS_RE + r")",
        lambda m: m.group(1) + " \u2013 " + m.group(2),
        text_out,
        flags=re.IGNORECASE,
    )

    # (2) Merge split digit sequences that arise when each glyph is its own BT
    #     block: "202 4" → "2024", "20 18" → "2018".
    text_out = re.sub(r'(?<!\d)(\d{2,3}) (\d)(?!\d)', r'\1\2', text_out)
    text_out = re.sub(r'(?<!\d)(\d{2}) (\d{2})(?!\d)', r'\1\2', text_out)

    # (3) Collapse multiple consecutive spaces to one (space-sentinel artefact).
    text_out = re.sub(r'[ \t]+', ' ', text_out)
    # Re-strip each line after collapsing spaces.
    text_out = "\n".join(line.strip() for line in text_out.splitlines())

    return text_out


# ---------------------------------------------------------------------------
# PDF parser  (pypdf preferred; stdlib fallback if not installed)
# ---------------------------------------------------------------------------

def _parse_with_claude(text: str, source: str) -> Profile:
    """
    Use Claude to parse raw extracted resume text into a structured Profile.

    This is the primary parsing strategy for PDF input: PDF is a rendering
    format with no semantic structure, so regex heuristics are inherently
    fragile.  Claude reads the raw text and returns JSON, handling word
    splits, encoding artefacts, ambiguous separators, and multi-column
    layouts correctly in a single pass.

    Falls back to _parse_plain_resume_text on any API/parsing error.
    """
    import json
    import os

    try:
        from anthropic import Anthropic
    except ImportError:
        return _parse_plain_resume_text(text, source=source)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _parse_plain_resume_text(text, source=source)

    prompt = f"""You are a resume parser. The text below was extracted from a PDF resume.
PDF text extraction is lossy: words may be split ("Mi ssouri" = "Missouri",
"Zomat o" = "Zomato"), characters may be garbled, and layout cues are lost.
Use context to reconstruct the correct meaning.

Return ONLY a JSON object — no markdown, no explanation — with this exact schema:
{{
  "experience": [
    {{
      "title": "Job title",
      "company": "Company name (reconstruct split words)",
      "start": "Month YYYY or YYYY",
      "end": "Month YYYY or YYYY or Present",
      "location": "City, State",
      "bullets": ["bullet text 1", "bullet text 2"]
    }}
  ],
  "projects": [
    {{
      "name": "Project name",
      "tech": ["tech1", "tech2"],
      "bullets": ["bullet text 1"]
    }}
  ],
  "skills": ["skill1", "skill2"],
  "education": [
    {{
      "institution": "University name",
      "degree": "Degree and field",
      "dates": "YYYY – YYYY",
      "location": ""
    }}
  ],
  "certifications": ["cert1"]
}}

RESUME TEXT:
{text}"""

    try:
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        data = json.loads(raw)
    except Exception:
        return _parse_plain_resume_text(text, source=source)

    profile = Profile()

    for r in data.get("experience", []):
        bullets = [
            Bullet(
                text=b,
                metrics=extract_metrics(b),
                tools=extract_tools(b),
                evidence_source=source,
                confidence=score_confidence(b),
            )
            for b in r.get("bullets", [])
            if isinstance(b, str) and b.strip()
        ]
        profile.experience.append(Role(
            title=r.get("title", ""),
            company=r.get("company", ""),
            start=r.get("start", ""),
            end=r.get("end", ""),
            location=r.get("location", ""),
            bullets=bullets,
        ))

    for p in data.get("projects", []):
        bullets = [
            Bullet(
                text=b,
                metrics=extract_metrics(b),
                tools=extract_tools(b),
                evidence_source=source,
                confidence=score_confidence(b),
            )
            for b in p.get("bullets", [])
            if isinstance(b, str) and b.strip()
        ]
        profile.projects.append(Project(
            name=p.get("name", ""),
            tech=p.get("tech", []),
            bullets=bullets,
        ))

    profile.skills = _dedupe([s for s in data.get("skills", []) if isinstance(s, str)])
    profile.education = [
        {
            "institution": e.get("institution", ""),
            "degree": e.get("degree", ""),
            "dates": e.get("dates", ""),
            "location": e.get("location", ""),
        }
        for e in data.get("education", [])
    ]
    profile.certifications = [c for c in data.get("certifications", []) if isinstance(c, str)]

    return profile


def parse_pdf(file_bytes: bytes, source: str = "pdf_resume") -> Profile:
    """
    Extract text from a PDF file and parse it into a Profile.

    Text extraction: pypdf (if installed) → stdlib extractor.
    Parsing: Claude API (if ANTHROPIC_API_KEY set) → regex fallback.

    PDF has no semantic structure — Claude as the parser is more reliable
    than regex heuristics for any resume layout or encoding.
    """
    text = ""
    try:
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(file_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages)
    except ImportError:
        text = _extract_pdf_text_stdlib(file_bytes)

    if not text.strip():
        # pypdf gave nothing — try our stdlib extractor as a second attempt
        text = _extract_pdf_text_stdlib(file_bytes)

    if not text.strip():
        raise ValueError(
            "No text could be extracted from this PDF. "
            "It may be a scanned/image-only PDF. "
            "Try copy-pasting the text content instead."
        )

    if "\\resumeSubheading" in text or "\\resumeItem" in text:
        return parse_latex(text, source=source)

    # Claude-based parsing is the primary path; regex is the fallback.
    return _parse_with_claude(text, source=source)


# ---------------------------------------------------------------------------
# DOCX parser  (python-docx preferred; zipfile fallback if not installed)
# ---------------------------------------------------------------------------

def _extract_docx_text_stdlib(data: bytes) -> str:
    """Extract text from a .docx file using only stdlib (zipfile + xml.etree)."""
    import zipfile
    import xml.etree.ElementTree as ET
    import io

    NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    pieces: List[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            with z.open("word/document.xml") as f:
                tree = ET.parse(f)
            for para in tree.iter(f"{{{NS}}}p"):
                parts = [t.text or "" for t in para.iter(f"{{{NS}}}t")]
                line = "".join(parts).strip()
                if line:
                    pieces.append(line)
    except Exception:
        pass
    return "\n".join(pieces)


def parse_docx(file_bytes: bytes, source: str = "docx_resume") -> Profile:
    """
    Extract text from a .docx file and parse it.
    Uses python-docx if available, falls back to stdlib zipfile extraction.
    """
    text = ""
    try:
        from docx import Document
        import io
        doc = Document(io.BytesIO(file_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        text = "\n".join(paragraphs)
    except ImportError:
        text = _extract_docx_text_stdlib(file_bytes)

    if not text.strip():
        raise ValueError("No text could be extracted from this DOCX file.")

    return _parse_plain_resume_text(text, source=source)


# ---------------------------------------------------------------------------
# Plain text resume parser — handles PDF/DOCX extracted text
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
    # Exact match first
    for sec, aliases in _SECTION_HEADERS.items():
        if clean in aliases:
            return sec
    # Substring match: short, mostly-alpha lines that CONTAIN a known keyword
    # Handles "PROFESSIONAL EXPERIENCE", "TECHNICAL SKILLS", "WORK HISTORY", etc.
    if len(clean) < 50 and sum(c.isalpha() or c == " " for c in clean) / max(len(clean), 1) > 0.85:
        for sec, aliases in _SECTION_HEADERS.items():
            for alias in aliases:
                if alias in clean:
                    return sec
    return None


def _parse_plain_resume_text(text: str, source: str = "resume") -> Profile:
    """
    Parse plain text extracted from PDF or DOCX.
    Uses section-header detection + date-pattern heuristics to identify roles.
    Supports 1-line (Title  Company  Date), 2-line (Title+Company / Date),
    and 3-line (Title / Company / Date) role headers via 2-step lookahead.
    """
    profile = Profile()
    # Fix OT1 en-dash encoded as ASCII 't' (LaTeX CMR font glyph 0x74).
    # Applied here as a guaranteed fallback even if _extract_pdf_text_stdlib
    # couldn't apply it (e.g. when "2024 t Present" was split across lines).
    _months_alt = (r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
                   r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
                   r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?|Present|Current|Now")
    text = re.sub(r"(\d{4})\s+t\s+(" + _months_alt + r")",
                  lambda m: m.group(1) + " \u2013 " + m.group(2),
                  text, flags=re.IGNORECASE)
    # Also merge split year digits that the extractor may have left: "202 4"→"2024"
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

        # Detect section header
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
                # "Title  Company  Jan 2022 – Present" all on one line
                dm = date_here
                pre = s[:dm.start()].strip(" |·–—-")
                location = ""
                # Try "Title : Company, Location" (LaTeX resume colon style) first
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
                # 2-column LaTeX layout: company on the next line (no date, no section, no bullet)
                _is_bullet = lambda ln: (ln.startswith(("•", "-", "–", "*", "·", "○", "▪"))
                                         or bool(re.match(r'^x\s+\S', ln)))
                if (not company and next1
                        and not _detect_section(next1)
                        and not _DATE_PATTERN.search(next1)
                        and not _is_bullet(next1)):
                    loc_parts = re.split(r"\s{2,}", next1.strip())
                    company = loc_parts[0].strip()
                    location = loc_parts[1].strip() if len(loc_parts) > 1 else ""
                    i += 1  # consume company line
                current_role = Role(title=title, company=company, start=start, end=end, location=location)
                profile.experience.append(current_role)
                continue

            # "looks like a title" guard: short, starts uppercase, no bullet prefix
            _like_title = lambda ln: (
                bool(ln) and ln[0:1].isupper()
                and len(ln.split()) <= 8 and len(ln) <= 80
                and not re.match(r'^x\s+\S', ln)
                and not ln.startswith(("•", "-", "–", "*", "·", "○", "▪"))
            )

            if date_n1 and _like_title(s):
                # Title [+ company] on this line, date on next line
                parts = re.split(r"\s{2,}|\s*[|·–]\s*", s)
                title = parts[0].strip()
                company = parts[1].strip() if len(parts) > 1 else ""
                d = _DATE_PATTERN.search(next1)
                start, end = _parse_dates(d.group(0)) if d else ("", "")
                current_role = Role(title=title, company=company, start=start, end=end, location="")
                profile.experience.append(current_role)
                i += 1  # consume date line
                continue

            if date_n2 and next1 and not _detect_section(next1) and _like_title(s) and _like_title(next1):
                # 3-line pattern: Title / Company / Date
                title = s.strip()
                company = next1.strip()
                d = _DATE_PATTERN.search(next2)
                start, end = _parse_dates(d.group(0)) if d else ("", "")
                current_role = Role(title=title, company=company, start=start, end=end, location="")
                profile.experience.append(current_role)
                i += 2  # consume company and date lines
                continue

            # Bullet lines — standard prefixes OR "x " (LaTeX font glyph decoded as x)
            if current_role and (s.startswith(("•", "-", "–", "*", "·", "○", "▪"))
                                  or re.match(r'^x\s+\S', s)):
                txt = s.lstrip("•-–*·○▪x ").strip()
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
                if date_m or any(kw in s.lower() for kw in ("university", "college", "institute", "school", "master", "bachelor", "phd", "b.s", "m.s", "b.e", "m.e")):
                    profile.education.append({"institution": s, "degree": "", "dates": "", "location": ""})

        elif section == "skills":
            # Split on commas and semicolons; pipes separate categories, keep both sides
            for sk in re.split(r"[,;]", s):
                sk = sk.strip(" -*•·|")
                # Strip leading category label "Languages: Python SQL" → add each word
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
            # Project name lines start with a bullet prefix or look title-like
            is_proj_header = (s.startswith(("•", "-", "–", "*", "·", "○", "▪"))
                              or re.match(r'^x\s+\S', s))
            clean_s = s.lstrip("•-–*·○▪x ").strip()
            if is_proj_header and len(clean_s) > 3:
                proj = Project(name=clean_s, tech=extract_tools(clean_s))
                profile.projects.append(proj)
            elif profile.projects and clean_s and len(clean_s) > 10:
                # Description / bullet lines for the current project
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
# Auto-detect format from content
# ---------------------------------------------------------------------------

def auto_detect_format(text: str) -> str:
    """Detect format from content heuristics. Returns 'latex'|'markdown'|'blob'."""
    if "\\documentclass" in text or "\\resumeSubheading" in text or "\\resumeItem" in text:
        return "latex"
    if re.search(r"^#{1,3}\s+\w", text, re.MULTILINE):
        return "markdown"
    return "blob"


# ---------------------------------------------------------------------------
# Merge profiles
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Extract profile from resume artifact.")
    parser.add_argument("--input", required=True, help="Path to input file")
    parser.add_argument(
        "--format",
        choices=["markdown", "latex", "blob", "linkedin", "pdf", "docx", "auto"],
        default="auto",
        help="Input format (default: auto-detect)",
    )
    parser.add_argument("--output", default="-", help="Output JSON path (- for stdout)")
    args = parser.parse_args()

    with open(args.input, "rb") as f:
        raw = f.read()

    fmt = args.format
    if fmt in ("pdf",):
        profile = parse_pdf(raw)
    elif fmt in ("docx", "doc"):
        profile = parse_docx(raw)
    else:
        text = raw.decode("utf-8", errors="replace")
        if fmt == "auto":
            fmt = auto_detect_format(text)
        parsers = {
            "markdown": parse_markdown,
            "latex": parse_latex,
            "blob": parse_blob,
            "linkedin": parse_linkedin,
        }
        profile = parsers[fmt](text)

    result = json.dumps(profile_to_dict(profile), indent=2)
    if args.output == "-":
        print(result)
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)


if __name__ == "__main__":
    main()
