"""
parsers/__init__.py
Public API for the tailor-resume parser package.

All callers should import from here:
    from parsers import parse_latex, parse_pdf, parse_docx, parse_blob, parse_markdown
    from parsers import parse_linkedin, auto_detect_format, merge_profiles
"""
from .latex_parser import parse_latex
from .markdown_parser import parse_markdown
from .plain_parser import parse_blob, parse_linkedin, _parse_plain_resume_text
from .pdf_extractor import parse_pdf, _parse_with_claude, _enrich_profile_with_claude
from .docx_extractor import parse_docx
from .normalizer import auto_detect_format, merge_profiles, _dedupe, _parse_dates

__all__ = [
    "parse_latex",
    "parse_markdown",
    "parse_blob",
    "parse_linkedin",
    "parse_pdf",
    "parse_docx",
    "auto_detect_format",
    "merge_profiles",
    # Semi-private — exported for backward compat with callers that imported them
    "_parse_plain_resume_text",
    "_parse_with_claude",
    "_enrich_profile_with_claude",
    "_dedupe",
    "_parse_dates",
]
