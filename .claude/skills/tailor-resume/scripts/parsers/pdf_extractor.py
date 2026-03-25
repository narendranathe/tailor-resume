"""
pdf_extractor.py
Extract text from PDF bytes and parse into a canonical Profile.

Text extraction tier (first success wins):
    1. pdfminer.six  — reads ToUnicode CMap; best for LaTeX/CMR fonts
    2. pypdf          — fast; good for Word-generated PDFs
    3. stdlib         — no dependencies; last resort

After extraction, parsing is delegated to:
    - parse_latex()            if text contains LaTeX macros
    - _parse_plain_resume_text() otherwise (shared with docx_extractor)
    - _parse_with_claude()     if ANTHROPIC_API_KEY is set (Claude fallback)
    - _enrich_profile_with_claude() for optional enrichment pass
"""
from __future__ import annotations

import json
import re
from typing import List, Optional, Tuple

from resume_types import Bullet, Profile, Project, Role, profile_to_dict
from text_utils import extract_metrics, extract_tools, score_confidence
from parsers.plain_parser import _parse_plain_resume_text
from parsers.latex_parser import parse_latex
from parsers.normalizer import _dedupe


# ---------------------------------------------------------------------------
# OT1 font encoding artifacts
# ---------------------------------------------------------------------------

_OT1_MAP: dict = {
    "\x0c": "fi",
    "\x0d": "fl",
    "\x0e": "ff",
    "\x0f": "ffi",
    "\x10": "ffl",
    "\x7b": "\u2013",
    "\x7c": "\u2014",
    "\x95": "\u2022",
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
}

_OT1_ARTIFACT_ONLY = re.compile(r'^(ffi|j)\s*$')
_OT1_ARTIFACT_PREFIX = re.compile(r'^(ffi|j)\s+')


def _apply_ot1(s: str) -> str:
    """Substitute OT1-encoded bytes/ligature chars with readable equivalents."""
    for src, dst in _OT1_MAP.items():
        s = s.replace(src, dst)
    return s


def _normalize_ot1_artifacts(text: str) -> str:
    """
    Normalize OT1 font glyph artifacts that appear regardless of extraction tier.

    pypdf and the stdlib extractor both decode the CMR bullet glyph (0x0F) as
    "ffi" and icon-font separator glyphs as "j" when no ToUnicode CMap is present.
    """
    out: list[str] = []
    for line in text.splitlines():
        if _OT1_ARTIFACT_ONLY.match(line):
            continue
        line = _OT1_ARTIFACT_PREFIX.sub("• ", line)
        out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# PDF string helpers
# ---------------------------------------------------------------------------

def _pdf_read_string(block: str, pos: int) -> tuple:
    """
    Read a PDF literal string starting at pos (which should point at '(').
    Returns (content, new_pos). Handles nested parens and backslash escapes.
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
    Decode a PDF hex string <XXXX> as UTF-16-BE or latin-1.
    Tries UTF-16-BE and keeps it only when the result is ≥ 75% ASCII printable.
    """
    hex_str = re.sub(r"\s+", "", hex_str)
    if len(hex_str) % 2 != 0:
        hex_str += "0"
    try:
        raw = bytes.fromhex(hex_str)
    except ValueError:
        return ""
    if len(raw) >= 2 and len(raw) % 2 == 0:
        try:
            text = raw.decode("utf-16-be", errors="strict")
            ascii_printable = sum(1 for c in text if 32 <= ord(c) <= 126)
            if ascii_printable >= len(text) * 0.75:
                return text
        except Exception:
            pass
    return "".join(chr(b) for b in raw if chr(b).isprintable())


# ---------------------------------------------------------------------------
# Stdlib PDF extractor
# ---------------------------------------------------------------------------

def _extract_pdf_text_stdlib(data: bytes) -> str:
    """
    Stdlib-only PDF text extractor. No regex on unbounded content.
    Handles FlateDecode, absolute Tm positioning, TJ/Tj operators.
    """
    import zlib

    raw_streams: List[bytes] = []
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.DOTALL):
        s = m.group(1)
        try:
            raw_streams.append(zlib.decompress(s))
        except Exception:
            raw_streams.append(s)
    if not raw_streams:
        raw_streams = [data]

    pieces: List[Tuple[float, float, str]] = []

    def _parse_tj_array(arr: str) -> str:
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
            tm_x = 0.0
            tm_y = 0.0
            td_x = 0.0
            td_y = 0.0
            leading = 12.0
            current: List[str] = []

            def emit(txt_pieces: List[str], cx: float, cy: float) -> None:
                joined = "".join(txt_pieces)
                if joined.strip():
                    pieces.append((cx, cy, joined))

            while pos < n:
                c = block[pos]

                if c in " \t\r\n":
                    pos += 1
                    continue

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

                m2 = re.match(r"(-?\d+(?:\.\d*)?)\s+TL", block[pos:])
                if m2:
                    try:
                        leading = abs(float(m2.group(1)))
                    except ValueError:
                        pass
                    pos += m2.end()
                    continue

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

                if block[pos:pos+2] == "T*":
                    if current:
                        emit(current, tm_x + td_x, tm_y + td_y)
                        current = []
                    td_y -= leading
                    pos += 2
                    continue

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

                m2 = re.match(r"[^\s\[(<]+", block[pos:])
                if m2:
                    pos += m2.end()
                else:
                    pos += 1

            if current:
                emit(current, tm_x + td_x, tm_y + td_y)

    def _unescape(s: str) -> str:
        s = (s.replace("\\n", " ").replace("\\r", " ")
              .replace("\\t", " ").replace("\\(", "(")
              .replace("\\)", ")").replace("\\\\", "\\"))
        s = re.sub(r"\\([0-7]{1,3})", lambda m: chr(int(m.group(1), 8) % 128), s)
        return s

    cleaned_pieces: List[Tuple[float, float, str]] = []
    for px, py, ptxt in pieces:
        ptxt = _unescape(ptxt)
        ptxt = _apply_ot1(ptxt)
        ptxt_p = "".join(c for c in ptxt if c.isprintable())
        if not ptxt_p:
            continue
        stored = " " if not ptxt_p.strip() else ptxt_p
        cleaned_pieces.append((px, py, stored))

    if not cleaned_pieces:
        return ""

    Y_TOL = 3.0
    CHAR_W = 4.0

    def _group_to_lines(ps: List[Tuple[float, float, str]]) -> List[str]:
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

    col_split_x: Optional[float] = None
    if len(cleaned_pieces) > 4:
        all_xs_g = sorted(p[0] for p in cleaned_pieces)
        max_gap_g = 0.0
        for i in range(1, len(all_xs_g)):
            gap = all_xs_g[i] - all_xs_g[i - 1]
            if gap > max_gap_g:
                max_gap_g = gap
                col_split_x = (all_xs_g[i] + all_xs_g[i - 1]) / 2.0
        if max_gap_g < 18.0:
            col_split_x = None

    if col_split_x is not None:
        left_pieces = [(x, y, t) for x, y, t in cleaned_pieces if x < col_split_x]
        right_pieces = [(x, y, t) for x, y, t in cleaned_pieces if x >= col_split_x]
        lines_out = _group_to_lines(left_pieces) + _group_to_lines(right_pieces)
    else:
        lines_out = _group_to_lines(cleaned_pieces)

    cleaned: List[str] = []
    for line in lines_out:
        if len(line) < 2:
            continue
        alpha = sum(c.isalpha() for c in line)
        if alpha / len(line) < 0.25 and not re.search(r"\d", line):
            continue
        cleaned.append(line)

    text_out = "\n".join(cleaned)

    _MONTHS_RE = (r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
                  r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
                  r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?|Present|Current|Now")
    text_out = re.sub(
        r"(\d{4})\s+t\s+(" + _MONTHS_RE + r")",
        lambda m: m.group(1) + " \u2013 " + m.group(2),
        text_out,
        flags=re.IGNORECASE,
    )
    text_out = re.sub(r'(?<!\d)(\d{2,3}) (\d)(?!\d)', r'\1\2', text_out)
    text_out = re.sub(r'(?<!\d)(\d{2}) (\d{2})(?!\d)', r'\1\2', text_out)
    text_out = re.sub(r'[ \t]+', ' ', text_out)
    text_out = "\n".join(line.strip() for line in text_out.splitlines())
    text_out = _normalize_ot1_artifacts(text_out)

    return text_out


# ---------------------------------------------------------------------------
# pdfminer extractor
# ---------------------------------------------------------------------------

def _split_bullet_block(text: str) -> List[str]:
    """Split a multi-sentence paragraph block into individual bullet strings."""
    sentences: List[str] = []
    current: List[str] = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            if current:
                sentences.append(" ".join(current))
                current = []
            continue
        if current and current[-1].rstrip().endswith(".") and line[0].isupper():
            sentences.append(" ".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        sentences.append(" ".join(current))
    return [s for s in sentences if s]


def _extract_pdf_text_pdfminer(data: bytes) -> str:
    """Extract text from a PDF using pdfminer.six with column-aware reconstruction."""
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTTextBox
    import io

    laparams = LAParams(char_margin=1.5, line_margin=0.3, word_margin=0.05, boxes_flow=0.5)
    boxes: List[Tuple[float, float, str]] = []
    for page_layout in extract_pages(io.BytesIO(data), laparams=laparams):
        for element in page_layout:
            if isinstance(element, LTTextBox):
                text = element.get_text().strip()
                if text:
                    boxes.append((element.y1, element.x0, text))

    if not boxes:
        return ""

    try:
        first_page = next(extract_pages(io.BytesIO(data), laparams=laparams))
        page_mid = first_page.width / 2.0
    except Exception:
        page_mid = 306.0

    x0_vals = sorted(set(round(b[1]) for b in boxes))
    split_x: Optional[float] = None
    if len(x0_vals) >= 2:
        max_gap, best_i = 0, 0
        for i in range(len(x0_vals) - 1):
            if x0_vals[i + 1] > page_mid:
                break
            gap = x0_vals[i + 1] - x0_vals[i]
            if gap > max_gap:
                max_gap, best_i = gap, i
        if max_gap > 15:
            split_x = (x0_vals[best_i] + x0_vals[best_i + 1]) / 2.0

    def _box_lines(text: str) -> List[str]:
        sentences = _split_bullet_block(text)
        if len(sentences) > 1:
            return ["• " + s for s in sentences]
        return [ln.strip() for ln in text.split("\n") if ln.strip()]

    parts: List[str] = []
    if split_x is not None:
        left = [(y1, x0, t) for y1, x0, t in boxes if x0 < split_x]
        right = [(y1, x0, t) for y1, x0, t in boxes if x0 >= split_x]
        left.sort(key=lambda b: (-b[0], b[1]))
        right.sort(key=lambda b: (-b[0], b[1]))
        for _, _, text in right:
            parts.extend(_box_lines(text))
        parts.append("")
        for _, _, text in left:
            parts.extend(_box_lines(text))
    else:
        boxes.sort(key=lambda b: (-b[0], b[1]))
        for _, _, text in boxes:
            parts.extend(_box_lines(text))

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Claude parsing helpers
# ---------------------------------------------------------------------------

def _parse_with_claude(text: str, source: str) -> Profile:
    """Use Claude to parse raw extracted resume text into a structured Profile."""
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


def _enrich_profile_with_claude(profile: Profile, source: str = "") -> Profile:
    """
    Enrich an already-parsed Profile using Claude as a resume coach.
    Second pass — called AFTER parse_pdf() has produced a clean Profile.
    Falls back to the original profile on any API error.
    """
    import os

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return profile

    try:
        from anthropic import Anthropic
    except ImportError:
        return profile

    try:
        profile_dict = profile_to_dict(profile)
        profile_json = json.dumps(profile_dict, indent=2)

        prompt = f"""You are a resume coach. The JSON below is a structured resume profile.
Your job is to IMPROVE it — do NOT invent facts, do NOT change numbers, do NOT fabricate metrics.

Instructions:
1. Rewrite weak bullets into stronger STAR format (active voice, quantified impact).
   Only rewrite if the original is passive / vague — preserve strong bullets verbatim.
2. For each bullet, set the "confidence" field to "high" (clear quantified evidence),
   "medium" (some evidence), or "low" (vague claim, no numbers, or passive voice).
3. Add to the "skills" list any skills you see mentioned in bullets that are not
   already listed there.

Return ONLY valid JSON with the same schema. No markdown, no explanation.

PROFILE:
{profile_json}"""

        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        data = json.loads(raw)
    except Exception:
        return profile

    enriched = Profile()
    for r in data.get("experience", []):
        bullets = [
            Bullet(
                text=b if isinstance(b, str) else b.get("text", ""),
                metrics=extract_metrics(b if isinstance(b, str) else b.get("text", "")),
                tools=extract_tools(b if isinstance(b, str) else b.get("text", "")),
                evidence_source=source or "claude_enrichment",
                confidence=(b.get("confidence", "medium") if isinstance(b, dict) else "medium"),
            )
            for b in r.get("bullets", [])
            if b
        ]
        enriched.experience.append(Role(
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
                text=b if isinstance(b, str) else b.get("text", ""),
                metrics=extract_metrics(b if isinstance(b, str) else b.get("text", "")),
                tools=extract_tools(b if isinstance(b, str) else b.get("text", "")),
                evidence_source=source or "claude_enrichment",
                confidence="medium",
            )
            for b in p.get("bullets", [])
            if b
        ]
        enriched.projects.append(Project(
            name=p.get("name", ""),
            tech=p.get("tech", []),
            bullets=bullets,
        ))

    enriched.skills = _dedupe([s for s in data.get("skills", []) if isinstance(s, str)])
    enriched.education = [
        {
            "institution": e.get("institution", ""),
            "degree": e.get("degree", ""),
            "dates": e.get("dates", ""),
            "location": e.get("location", ""),
        }
        for e in data.get("education", [])
    ]
    enriched.certifications = [c for c in data.get("certifications", []) if isinstance(c, str)]
    return enriched


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_pdf(file_bytes: bytes, source: str = "pdf_resume") -> Profile:
    """
    Extract text from a PDF file and parse it into a Profile.

    Text extraction tier (first success wins):
        1. pdfminer.six — reads ToUnicode CMap; best for LaTeX/CMR fonts
        2. pypdf         — fast; good for Word-generated PDFs
        3. stdlib        — no dependencies; last resort
    """
    text = ""

    try:
        text = _extract_pdf_text_pdfminer(file_bytes)
    except Exception:
        pass

    if not text.strip():
        try:
            from pypdf import PdfReader
            import io
            reader = PdfReader(io.BytesIO(file_bytes))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n".join(pages)
        except ImportError:
            pass

    if not text.strip():
        text = _extract_pdf_text_stdlib(file_bytes)

    if not text.strip():
        raise ValueError(
            "No text could be extracted from this PDF. "
            "It may be a scanned/image-only PDF. "
            "Try copy-pasting the text content instead."
        )

    text = _normalize_ot1_artifacts(text)

    if "\\resumeSubheading" in text or "\\resumeItem" in text:
        return parse_latex(text, source=source)

    return _parse_plain_resume_text(text, source=source)
