"""
app/routes/resume.py
Resume-tailoring endpoints.

POST /resume/tailor  — upload artifact + JD → tailored PDF/tex + ATS score
GET  /health         — liveness probe
"""
from __future__ import annotations

import base64
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel

from app.auth import get_current_user
from app.config import settings
from app.middleware.usage import check_usage, increment_usage

router = APIRouter(tags=["resume"])

# ---------------------------------------------------------------------------
# File-size limit (FIX 2)
# ---------------------------------------------------------------------------

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

# ---------------------------------------------------------------------------
# Per-IP rate limiting (FIX 2)
# Try slowapi first; fall back to in-memory dict.
# ---------------------------------------------------------------------------

try:
    from slowapi import Limiter  # type: ignore
    from slowapi.util import get_remote_address  # type: ignore
    _limiter = Limiter(key_func=get_remote_address)
    _HAS_SLOWAPI = True
except ImportError:
    _limiter = None
    _HAS_SLOWAPI = False

# In-memory rate bucket (used when slowapi is not available)
_rate_buckets: dict = defaultdict(list)


def _check_rate(ip: str, limit: int = 10, window: int = 60) -> bool:
    """Return True if the request is within the rate limit, False if exceeded."""
    now = time.time()
    bucket = [t for t in _rate_buckets[ip] if now - t < window]
    _rate_buckets[ip] = bucket
    if len(bucket) >= limit:
        return False
    _rate_buckets[ip].append(now)
    return True


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class TailorResponse(BaseModel):
    ats_score: float
    gap_summary: str
    report: str
    tex_b64: Optional[str] = None   # base64-encoded .tex if compiled
    docx_b64: Optional[str] = None  # base64-encoded .docx if available (FIX 3)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/health")
async def health():
    return {"status": "ok", "version": settings.API_VERSION}


@router.post("/resume/tailor", response_model=TailorResponse)
async def tailor_resume(
    request: Request,
    jd_text: str = Form(..., description="Job description text"),
    artifact: UploadFile = File(..., description="Resume file (PDF, DOCX, LaTeX, Markdown, or plain text)"),
    user_id: str = Depends(get_current_user),
):
    """
    Accept a job description + resume artifact, run the tailor-resume pipeline,
    and return ATS score, gap summary, report, and (optionally) the compiled LaTeX
    and DOCX outputs.
    """
    # FIX 2a — file size guard
    content = await artifact.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Max size: 10 MB.",
        )
    # Reset cursor so downstream consumers can re-read
    await artifact.seek(0)

    # FIX 2b — per-IP rate limiting
    client_ip = request.client.host if request.client else "unknown"
    if _HAS_SLOWAPI:
        # slowapi decorates at the route level; the fallback below is for safety
        pass
    else:
        if not _check_rate(client_ip):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
            )

    # Enforce usage limits before running the pipeline
    check_usage(user_id)

    artifact_bytes = content  # already read above
    artifact_filename = artifact.filename or "resume"

    # Determine format from filename extension
    ext = Path(artifact_filename).suffix.lower()
    format_map = {
        ".pdf": "pdf",
        ".docx": "docx",
        ".doc": "docx",
        ".tex": "latex",
        ".md": "markdown",
        ".txt": "plain",
    }
    artifact_format = format_map.get(ext, "plain")

    try:
        result = _run_pipeline(jd_text, artifact_bytes, artifact_format, artifact_filename)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Pipeline error: {exc}",
        ) from exc

    # Pipeline succeeded — record the usage
    increment_usage(user_id)

    # Read generated .tex if it exists
    tex_b64 = None
    if result.output_path and Path(result.output_path).exists():
        tex_b64 = base64.b64encode(Path(result.output_path).read_bytes()).decode()

    # FIX 3 — DOCX output: attempt to build a DOCX from the profile dict
    docx_b64 = None
    try:
        profile_dict = getattr(result, "profile_dict", None)
        if profile_dict is not None:
            from latex_renderer import build_docx_from_profile  # type: ignore
            docx_bytes = build_docx_from_profile(profile_dict)
            if docx_bytes:
                docx_b64 = base64.b64encode(docx_bytes).decode()
    except (ImportError, AttributeError):
        # build_docx_from_profile not yet implemented — field stays None
        pass

    return TailorResponse(
        ats_score=result.ats_score,
        gap_summary=result.gap_summary,
        report=result.report,
        tex_b64=tex_b64,
        docx_b64=docx_b64,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Formats that execute_text understands natively (text-in → profile)
_TEXT_FORMATS = {"plain", "markdown", "latex"}
# Alias: the pipeline calls plain text "blob"
_PIPELINE_FORMAT = {"plain": "blob", "markdown": "markdown", "latex": "latex"}

# Map from web format name to pipeline tuple format name (for binary files)
_BINARY_PIPELINE_FORMAT = {
    "pdf": "pdf",
    "docx": "docx",
}


def _run_pipeline(jd_text: str, artifact_bytes: bytes, artifact_format: str, filename: str):
    """
    Route bytes + format to the right pipeline entry point.

    - PDF / DOCX: save to a temp file and use execute(TailorConfig)
    - Text formats: decode and use execute_text
    """
    if artifact_format in _TEXT_FORMATS:
        from pipeline import execute_text  # tailor-resume scripts

        artifact_text = artifact_bytes.decode("utf-8", errors="replace")
        pipeline_fmt = _PIPELINE_FORMAT[artifact_format]
        return execute_text(jd_text=jd_text, artifact_text=artifact_text, artifact_format=pipeline_fmt)

    # Binary formats — write temp file and use file-based pipeline
    import os
    from pipeline import TailorConfig, execute  # tailor-resume scripts

    # FIX 1: determine the pipeline format name for this file type
    suffix = Path(filename).suffix.lower() or f".{artifact_format}"
    if suffix == ".pdf":
        detected_format = "pdf"
    elif suffix in (".docx", ".doc"):
        detected_format = "docx"
    elif suffix == ".md":
        detected_format = "markdown"
    else:
        detected_format = "blob"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(artifact_bytes)
        tmp_path = tmp.name

    try:
        # FIX 1: artifacts must be List[Tuple[str, str]] — (file_path, format_name)
        cfg = TailorConfig(
            jd_text=jd_text,
            artifacts=[(tmp_path, detected_format)],
            output_path=str(Path(tmp_path).parent / "resume.tex"),
        )
        return execute(cfg)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
