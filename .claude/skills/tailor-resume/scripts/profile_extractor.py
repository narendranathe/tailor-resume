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

def _extract_pdf_text_stdlib(data: bytes) -> str:
    """
    Extract readable text from a PDF using only stdlib.
    Parses PDF content streams for BT/ET text blocks and Tj/TJ operators.
    Works for most text-based PDFs (not scanned/image-only PDFs).
    """
    import zlib

    # Decompress FlateDecode streams, then scan for text operators
    text_pieces: List[str] = []

    # Try to decompress any zlib-compressed streams
    raw = data
    for chunk in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.DOTALL):
        stream = chunk.group(1)
        try:
            decompressed = zlib.decompress(stream)
            raw = raw + b"\n" + decompressed
        except Exception:
            pass  # not a compressed stream

    try:
        text = raw.decode("latin-1", errors="replace")
    except Exception:
        text = raw.decode("utf-8", errors="replace")

    # Extract text from BT...ET blocks
    for block in re.finditer(r"BT(.*?)ET", text, re.DOTALL):
        content = block.group(1)
        # Tj operator: (text) Tj
        for m in re.finditer(r"\(((?:[^()\\]|\\[()\\nrt])*)\)\s*Tj", content):
            text_pieces.append(m.group(1))
        # TJ operator: [(text) ...] TJ
        for m in re.finditer(r"\[(.*?)\]\s*TJ", content, re.DOTALL):
            for s in re.finditer(r"\(((?:[^()\\]|\\[()\\nrt])*)\)", m.group(1)):
                text_pieces.append(s.group(1))

    # Also try ' and " operators
    for m in re.finditer(r"\(((?:[^()\\]|\\[()\\nrt])*)\)\s*['\"]", text):
        text_pieces.append(m.group(1))

    # Clean PDF escape sequences
    cleaned: List[str] = []
    for piece in text_pieces:
        piece = (piece.replace("\\n", "\n").replace("\\r", "\n")
                 .replace("\\t", " ").replace("\\(", "(").replace("\\)", ")")
                 .replace("\\\\", "\\"))
        # Keep printable ASCII + newlines
        piece = "".join(c for c in piece if 32 <= ord(c) <= 126 or c == "\n")
        if piece.strip():
            cleaned.append(piece)

    return "\n".join(cleaned)


# ---------------------------------------------------------------------------
# PDF parser  (pypdf preferred; stdlib fallback if not installed)
# ---------------------------------------------------------------------------

def parse_pdf(file_bytes: bytes, source: str = "pdf_resume") -> Profile:
    """
    Extract text from a PDF file and parse it.
    Uses pypdf if available, falls back to stdlib extraction otherwise.
    """
    text = ""
    try:
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(file_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages)
    except ImportError:
        # No pypdf — use stdlib extractor
        text = _extract_pdf_text_stdlib(file_bytes)

    if not text.strip():
        raise ValueError(
            "No text could be extracted from this PDF. "
            "It may be a scanned/image-only PDF. "
            "Try copy-pasting the text content instead."
        )

    if "\\resumeSubheading" in text or "\\resumeItem" in text:
        return parse_latex(text, source=source)

    return _parse_plain_resume_text(text, source=source)


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
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?|Q[1-4])[\s,]*\d{2,4}|"
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
    return None


def _parse_plain_resume_text(text: str, source: str = "resume") -> Profile:
    """
    Parse plain text extracted from PDF or DOCX.
    Uses section-header detection + date-pattern heuristics to identify roles.
    """
    profile = Profile()
    lines = text.splitlines()
    section = "experience"
    current_role: Optional[Role] = None

    i = 0
    while i < len(lines):
        raw = lines[i]
        s = raw.strip()
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
            # A line followed by a date-range line is likely a role header
            date_in_line = _DATE_PATTERN.search(s)
            next_line = lines[i].strip() if i < len(lines) else ""
            date_in_next = _DATE_PATTERN.search(next_line) if next_line else None

            if date_in_line or date_in_next:
                # This line (or next) contains dates — likely "Title | Company | Date" or stacked
                if date_in_line:
                    # Try "Title  Company  Jan 2022 – Present" on same line
                    date_match = _DATE_PATTERN.search(s)
                    pre = s[:date_match.start()].strip(" |·–—-")
                    parts = re.split(r"\s{2,}|\s*[|·]\s*", pre)
                    title = parts[0].strip() if parts else pre
                    company = parts[1].strip() if len(parts) > 1 else ""
                    dates = date_match.group(0)
                    start, end = _parse_dates(dates)
                    current_role = Role(title=title, company=company, start=start, end=end, location="")
                    profile.experience.append(current_role)
                else:
                    # Title on this line, date on next
                    parts = re.split(r"\s{2,}|\s*[|·]\s*", s)
                    title = parts[0].strip()
                    company = parts[1].strip() if len(parts) > 1 else ""
                    date_str = next_line
                    d = _DATE_PATTERN.search(date_str)
                    start, end = _parse_dates(d.group(0)) if d else ("", "")
                    current_role = Role(title=title, company=company, start=start, end=end, location="")
                    profile.experience.append(current_role)
                    i += 1  # consume the date line
                continue

            # Bullet lines
            if current_role and (s.startswith(("•", "-", "–", "*", "·")) or (len(s) > 20 and s[0].isupper())):
                txt = s.lstrip("•-–*· ").strip()
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
            if s and not s.startswith(("•", "-")):
                date_m = _DATE_PATTERN.search(s)
                if date_m or any(kw in s.lower() for kw in ("university", "college", "institute", "school", "master", "bachelor", "phd")):
                    profile.education.append({"institution": s, "degree": "", "dates": "", "location": ""})

        elif section == "skills":
            for sk in re.split(r"[,;|•·\n]", s):
                sk = sk.strip(" -*•·")
                if sk and len(sk) > 1:
                    profile.skills.append(sk)

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
