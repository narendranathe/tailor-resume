"""
profile_extractor.py — compatibility shim.

All parser logic has moved to ``scripts/parsers/``.
This module re-exports everything so existing callers require no changes.

New code should import directly from the sub-modules:
    from parsers import parse_latex, parse_pdf, parse_docx
    from parsers import parse_blob, parse_markdown, parse_linkedin
    from parsers import auto_detect_format, merge_profiles
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure scripts/ is on the path when run as a standalone script
_SCRIPTS = Path(__file__).parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from parsers import (  # noqa: E402
    auto_detect_format,
    merge_profiles,
    parse_blob,
    parse_docx,
    parse_latex,
    parse_linkedin,
    parse_markdown,
    parse_pdf,
    _dedupe,
    _parse_dates,
    _parse_plain_resume_text,
)
from parsers.latex_parser import (  # noqa: E402
    _clean_latex,
    _extract_args,
    _split_sections_latex,
)
from parsers.pdf_extractor import (  # noqa: E402
    _OT1_ARTIFACT_ONLY,
    _OT1_ARTIFACT_PREFIX,
    _apply_ot1,
    _enrich_profile_with_claude,
    _extract_pdf_text_pdfminer,
    _extract_pdf_text_stdlib,
    _normalize_ot1_artifacts,
    _parse_with_claude,
    _split_bullet_block,
)
from parsers.plain_parser import _detect_section, _is_bullet_line  # noqa: E402
from resume_types import Profile, Role, profile_to_dict  # noqa: E402
from text_utils import extract_metrics, extract_tools, score_confidence  # noqa: E402

__all__ = [
    # Public parsers
    "parse_latex", "parse_blob", "parse_markdown", "parse_linkedin",
    "parse_pdf", "parse_docx", "auto_detect_format", "merge_profiles",
    # Types (re-exported so callers don't need to know about resume_types)
    "Profile", "Role", "profile_to_dict",
    # Utilities (re-exported so callers don't need to know about text_utils)
    "extract_metrics", "extract_tools", "score_confidence",
    # Semi-private — re-exported for backward compat with existing tests/callers
    "_extract_args", "_clean_latex", "_split_sections_latex",
    "_apply_ot1", "_extract_pdf_text_pdfminer", "_extract_pdf_text_stdlib", "_split_bullet_block",
    "_OT1_ARTIFACT_ONLY", "_OT1_ARTIFACT_PREFIX", "_normalize_ot1_artifacts",
    "_detect_section", "_is_bullet_line",
    "_dedupe", "_parse_dates", "_parse_plain_resume_text",
    "_parse_with_claude", "_enrich_profile_with_claude",
]

_PARSERS = {
    "markdown": parse_markdown,
    "latex": parse_latex,
    "blob": parse_blob,
    "linkedin": parse_linkedin,
}


def parse_pdf(file_bytes: bytes, source: str = "pdf_resume"):  # type: ignore[misc]
    """
    Monkeypatch-forwarding shim for parse_pdf.

    Tests that do ``monkeypatch.setattr(profile_extractor, "_extract_pdf_text_pdfminer", fake)``
    set the attribute on *this* module.  But the real implementation lives in
    ``parsers.pdf_extractor`` and calls its own module-level reference — so the patch
    is invisible to it.  This wrapper detects when the shim's reference has been
    overridden and temporarily forwards it into the implementation module so that
    ``parsers.pdf_extractor.parse_pdf`` picks it up.
    """
    import sys
    import parsers.pdf_extractor as _ext

    me = sys.modules[__name__]
    my_pdfminer = getattr(me, "_extract_pdf_text_pdfminer", None)
    original = _ext._extract_pdf_text_pdfminer

    if my_pdfminer is not None and my_pdfminer is not original:
        _ext._extract_pdf_text_pdfminer = my_pdfminer
        try:
            return _ext.parse_pdf(file_bytes, source)
        finally:
            _ext._extract_pdf_text_pdfminer = original

    return _ext.parse_pdf(file_bytes, source)


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
    if fmt == "pdf":
        profile = parse_pdf(raw)
    elif fmt in ("docx", "doc"):
        profile = parse_docx(raw)
    else:
        text = raw.decode("utf-8", errors="replace")
        if fmt == "auto":
            fmt = auto_detect_format(text)
        profile = _PARSERS[fmt](text)

    result = json.dumps(profile_to_dict(profile), indent=2)
    if args.output == "-":
        print(result)
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)


if __name__ == "__main__":
    main()
