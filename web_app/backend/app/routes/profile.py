"""
app/routes/profile.py
Profile persistence endpoints — Issue #39.

GET  /profile        — fetch stored profile for current user
POST /profile        — upsert profile (parsed from artifact)
DELETE /profile      — remove stored profile
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.auth import get_current_user
from app.db.supabase import get_profile_store

# ---------------------------------------------------------------------------
# File-size limit (FIX 2)
# ---------------------------------------------------------------------------

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

router = APIRouter(tags=["profile"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ProfileResponse(BaseModel):
    user_id: str
    profile: Dict[str, Any]


class ProfilePatchRequest(BaseModel):
    patch: Dict[str, Any]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/profile", response_model=ProfileResponse)
async def get_profile(user_id: str = Depends(get_current_user)):
    store = get_profile_store()
    profile = store.get(user_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return ProfileResponse(user_id=user_id, profile=profile)


@router.post("/profile", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
async def upsert_profile(
    artifact: UploadFile = File(..., description="Resume artifact to parse and store"),
    user_id: str = Depends(get_current_user),
):
    """
    Parse the uploaded resume artifact into a Profile dict and persist it.
    On subsequent tailoring calls, the stored profile is loaded automatically.
    """
    from pathlib import Path

    artifact_bytes = await artifact.read()
    # FIX 2 — file size guard
    if len(artifact_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Max size: 10 MB.",
        )
    artifact_filename = artifact.filename or "resume"
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
        profile_dict = _parse_to_dict(artifact_bytes, artifact_format)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Parse error: {exc}",
        ) from exc

    store = get_profile_store()
    store.upsert(user_id, profile_dict)
    return ProfileResponse(user_id=user_id, profile=profile_dict)


@router.delete("/profile", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(user_id: str = Depends(get_current_user)):
    store = get_profile_store()
    store.delete(user_id)


@router.patch("/profile", response_model=ProfileResponse)
async def patch_profile(
    payload: ProfilePatchRequest,
    user_id: str = Depends(get_current_user),
):
    """
    Apply a partial Profile patch — Epic #91 (M4).

    Deep-merges dicts; lists in `patch` replace lists in storage.
    404 if no Profile is stored yet.
    """
    store = get_profile_store()
    existing = store.get(user_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    merged = _deep_merge(existing, payload.patch or {})
    store.upsert(user_id, merged)
    return ProfileResponse(user_id=user_id, profile=merged)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """Recursive dict merge: dicts merge, lists/scalars in patch replace base."""
    result: Dict[str, Any] = dict(base)
    for key, value in patch.items():
        if (
            isinstance(value, dict)
            and isinstance(result.get(key), dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _parse_to_dict(artifact_bytes: bytes, artifact_format: str) -> Dict[str, Any]:
    """Parse resume bytes to a Profile dict using the tailor-resume parsers."""
    from parsers import (  # tailor-resume scripts
        parse_pdf,
        parse_docx,
        parse_latex,
        parse_markdown,
        parse_blob,
    )

    if artifact_format == "pdf":
        profile = parse_pdf(artifact_bytes)
    elif artifact_format == "docx":
        profile = parse_docx(artifact_bytes)
    else:
        text = artifact_bytes.decode("utf-8", errors="replace")
        if artifact_format == "latex":
            profile = parse_latex(text)
        elif artifact_format == "markdown":
            profile = parse_markdown(text)
        else:
            profile = parse_blob(text)

    return profile.__dict__ if hasattr(profile, "__dict__") else vars(profile)
