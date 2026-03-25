"""
docx_extractor.py
Extract text from DOCX bytes and parse into a canonical Profile.

Uses python-docx if available, falls back to stdlib zipfile + XML extraction.
Parsing delegated to plain_parser._parse_plain_resume_text (shared with pdf_extractor).
"""
from __future__ import annotations

from typing import List

from resume_types import Profile
from parsers.plain_parser import _parse_plain_resume_text


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
