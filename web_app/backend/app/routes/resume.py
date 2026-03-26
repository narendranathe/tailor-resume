"""
app/routes/resume.py
Resume-tailoring endpoints.

POST /resume/tailor  — upload artifact + JD → tailored PDF/tex + ATS score
GET  /health         — liveness probe
"""
from __future__ import annotations

import base64
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel

from app.auth import get_current_user
from app.config import settings
from app.middleware.usage import check_usage, increment_usage

router = APIRouter(tags=["resume"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class TailorResponse(BaseModel):
    ats_score: float
    gap_summary: str
    report: str
    tex_b64: Optional[str] = None   # base64-encoded .tex if compiled


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/health")
async def health():
    return {"status": "ok", "version": settings.API_VERSION}


@router.post("/resume/tailor", response_model=TailorResponse)
async def tailor_resume(
    jd_text: str = Form(..., description="Job description text"),
    artifact: UploadFile = File(..., description="Resume file (PDF, DOCX, LaTeX, Markdown, or plain text)"),
    user_id: str = Depends(get_current_user),
):
    """
    Accept a job description + resume artifact, run the tailor-resume pipeline,
    and return ATS score, gap summary, report, and (optionally) the compiled LaTeX.
    """
    # Enforce usage limits before running the pipeline
    check_usage(user_id)

    artifact_bytes = await artifact.read()
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

    return TailorResponse(
        ats_score=result.ats_score,
        gap_summary=result.gap_summary,
        report=result.report,
        tex_b64=tex_b64,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Formats that execute_text understands natively (text-in → profile)
_TEXT_FORMATS = {"plain", "markdown", "latex"}
# Alias: the pipeline calls plain text "blob"
_PIPELINE_FORMAT = {"plain": "blob", "markdown": "markdown", "latex": "latex"}


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
    import tempfile, os
    from pipeline import TailorConfig, execute  # tailor-resume scripts

    suffix = Path(filename).suffix or f".{artifact_format}"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(artifact_bytes)
        tmp_path = tmp.name

    try:
        cfg = TailorConfig(jd_text=jd_text, artifacts=[tmp_path])
        return execute(cfg)
    finally:
        os.unlink(tmp_path)
