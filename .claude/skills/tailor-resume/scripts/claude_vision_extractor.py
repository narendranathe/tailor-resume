"""
claude_vision_extractor.py
Tier-0 resume parser using Claude's vision and document API.

Handles any resume format including:
  - Scanned PDFs (image-based, no selectable text)
  - Image files (screenshots, photos of resumes: PNG, JPG, JPEG, GIF, WEBP)
  - LaTeX-generated PDFs with CMR fonts that mangle text extraction
  - Multi-column or complex-layout PDFs that confuse pdfminer/pypdf

All other extractors (pdfminer, pypdf, stdlib) operate on extracted text.
Claude reads the file as a human would -- understanding visual layout, tables,
columns, and implicit structure -- and returns fully structured profile JSON.

Usage:
    python claude_vision_extractor.py --input resume.pdf
    python claude_vision_extractor.py --input resume.png --output profile.json
    python claude_vision_extractor.py --input resume.jpg --model claude-opus-4-6

Requires:
    pip install anthropic>=0.40.0

Environment:
    ANTHROPIC_API_KEY -- required (or pass via --api-key flag)
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Supported media types
# ---------------------------------------------------------------------------

_EXTENSION_TO_MEDIA_TYPE: dict[str, str] = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

SUPPORTED_EXTENSIONS = set(_EXTENSION_TO_MEDIA_TYPE.keys())


# ---------------------------------------------------------------------------
# Extraction prompt
# ---------------------------------------------------------------------------

_EXTRACTION_PROMPT = """You are parsing a resume document. Extract ALL professional profile information and return it as structured JSON.

Rules:
- Extract ALL information VERBATIM -- do not summarize, paraphrase, or omit any detail
- Preserve all numbers, percentages, dollar amounts, dates, and metrics exactly as written
- Extract every bullet point under every role
- Order experience entries most-recent-first
- For skills: if grouped by category (e.g. "Languages:", "Tools:"), return a dict keyed by category; otherwise return a flat list
- If a field is absent, use empty string ("") or empty list ([])
- Return ONLY valid JSON -- no markdown fences, no explanation text, no preamble

Output schema:
{
  "experience": [
    {
      "title": "exact job title as written",
      "company": "exact company name",
      "start": "Mon YYYY or YYYY",
      "end": "Mon YYYY or Present",
      "location": "City, ST or Remote",
      "bullets": [
        {"text": "exact bullet text verbatim", "evidence_source": "vision", "confidence": "high"}
      ]
    }
  ],
  "projects": [
    {
      "name": "project name",
      "tech": ["tech1", "tech2"],
      "date": "YYYY or Mon YYYY",
      "bullets": [
        {"text": "exact bullet text verbatim", "evidence_source": "vision", "confidence": "high"}
      ]
    }
  ],
  "education": [
    {
      "school": "institution name",
      "degree": "full degree name and field",
      "dates": "YYYY-YYYY or Mon YYYY - Mon YYYY",
      "location": "City, ST"
    }
  ],
  "skills": {},
  "certifications": [],
  "summary": "professional summary text if present, else empty string"
}

Parse the resume now and return JSON only."""


# ---------------------------------------------------------------------------
# Core extraction functions
# ---------------------------------------------------------------------------

def _build_client(api_key: str | None = None):
    """Import anthropic and build a client. Raises ImportError with install hint if absent."""
    try:
        import anthropic  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "anthropic package is required for Tier-0 vision extraction.\n"
            "Install with: pip install 'anthropic>=0.40.0'\n"
            "Or: pip install -r requirements-optional.txt"
        ) from exc

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable is not set.\n"
            "Set it: export ANTHROPIC_API_KEY=sk-ant-..."
        )
    return anthropic.Anthropic(api_key=key)


def _encode_file(path: str) -> tuple[str, str]:
    """Read file and return (base64_string, media_type)."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    ext = file_path.suffix.lower()
    media_type = _EXTENSION_TO_MEDIA_TYPE.get(ext)
    if not media_type:
        raise ValueError(
            f"Unsupported file type: {ext}\n"
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    data = file_path.read_bytes()
    return base64.standard_b64encode(data).decode("utf-8"), media_type


def _build_content_block(base64_data: str, media_type: str) -> dict[str, Any]:
    """Build the Anthropic API content block for a file."""
    if media_type == "application/pdf":
        return {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": base64_data,
            },
        }
    # Images: PNG, JPG, GIF, WEBP
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64_data,
        },
    }


def _parse_response(text: str) -> dict:
    """Parse Claude JSON response, stripping markdown fences if present."""
    text = text.strip()
    # Strip ```json ... ``` if Claude added them despite instructions
    if text.startswith("```"):
        lines = text.splitlines()
        inner = lines[1:] if lines[0].startswith("```") else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        text = "\n".join(inner).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Claude returned invalid JSON. Raw response preview:\n{text[:500]}"
        ) from exc


def extract_from_bytes(
    data: bytes,
    media_type: str,
    model: str = "claude-sonnet-4-6",
    api_key: str | None = None,
) -> dict:
    """
    Extract a structured profile from raw file bytes.

    Args:
        data:       Raw file bytes (PDF or image).
        media_type: MIME type string e.g. 'application/pdf', 'image/png'.
        model:      Anthropic model ID. Defaults to claude-sonnet-4-6.
        api_key:    Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.

    Returns:
        Canonical profile dict matching resume_types.Profile schema.
    """
    client = _build_client(api_key)
    base64_data = base64.standard_b64encode(data).decode("utf-8")
    content_block = _build_content_block(base64_data, media_type)

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    content_block,
                    {"type": "text", "text": _EXTRACTION_PROMPT},
                ],
            }
        ],
    )

    raw_text = response.content[0].text
    return _parse_response(raw_text)


def extract_from_file(
    path: str,
    model: str = "claude-sonnet-4-6",
    api_key: str | None = None,
) -> dict:
    """
    Extract a structured profile from a PDF or image file.

    Tier-0 extraction -- highest fidelity. Uses Claude's native vision and document
    understanding to parse any resume format including scanned PDFs, image-based
    resumes, and screenshots. Falls back to Tier 1-3 (pdfminer/pypdf/stdlib) when
    this module or the anthropic package is absent.

    Args:
        path:    Path to a .pdf, .png, .jpg, .jpeg, .gif, or .webp file.
        model:   Anthropic model ID. Defaults to claude-sonnet-4-6.
        api_key: Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.

    Returns:
        Canonical profile dict:
        {
            "experience": [...],
            "projects": [...],
            "education": [...],
            "skills": {} or [...],
            "certifications": [...],
            "summary": "..."
        }

    Raises:
        FileNotFoundError: File does not exist.
        ValueError:        Unsupported file type or invalid JSON from Claude.
        ImportError:       anthropic package is not installed.
    """
    base64_data, media_type = _encode_file(path)
    data = base64.standard_b64decode(base64_data)
    return extract_from_bytes(data, media_type, model=model, api_key=api_key)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tier-0 resume parser using Claude vision/document API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python claude_vision_extractor.py --input resume.pdf
  python claude_vision_extractor.py --input resume.png --output profile.json
  python claude_vision_extractor.py --input linkedin_export.pdf --model claude-opus-4-6

Supported: PDF, PNG, JPG, JPEG, GIF, WEBP
Requires: ANTHROPIC_API_KEY environment variable
        """,
    )
    parser.add_argument("--input", required=True, help="Path to resume PDF or image file")
    parser.add_argument("--output", default=None, help="Output JSON path (default: stdout)")
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-6",
        help="Anthropic model ID (default: claude-sonnet-4-6)",
    )
    parser.add_argument("--api-key", default=None, dest="api_key", help="Anthropic API key")
    args = parser.parse_args()

    print(f"[tailor-resume] Tier-0 extraction: {args.input}", file=sys.stderr)
    print(f"[tailor-resume] Model: {args.model}", file=sys.stderr)

    profile = extract_from_file(args.input, model=args.model, api_key=args.api_key)
    output_json = json.dumps(profile, indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).write_text(output_json, encoding="utf-8")
        n_roles = len(profile.get("experience", []))
        n_projects = len(profile.get("projects", []))
        n_bullets = sum(len(r.get("bullets", [])) for r in profile.get("experience", []))
        print(f"[tailor-resume] Written to: {args.output}", file=sys.stderr)
        print(
            f"[tailor-resume] Extracted: {n_roles} roles, {n_projects} projects, "
            f"{n_bullets} bullets",
            file=sys.stderr,
        )
    else:
        print(output_json)


if __name__ == "__main__":
    main()
