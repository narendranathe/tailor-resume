"""
app/routes/setup.py
First-run setup wizard endpoints — Epic #91 (M3).

GET    /setup/state       — return the user's current wizard state
PUT    /setup/roles       — upsert target roles (1..5)
PUT    /setup/companies   — upsert target companies (1..100, soft warning ≥50)
POST   /setup/complete    — finalise the wizard
POST   /setup/skip        — record skip, keep wizard reachable
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.db.supabase import get_profile_store

router = APIRouter(tags=["setup"])

_MAX_ROLES = 5
_MAX_COMPANIES = 100
_SOFT_WARN_COMPANY_COUNT = 50
_SOURCE_CANONICAL = "canonical"
_SOURCE_CUSTOM = "custom"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class CompanyEntry(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    source: str = _SOURCE_CUSTOM


class SetupStateResponse(BaseModel):
    user_id: str
    target_roles: List[str]
    target_companies: List[CompanyEntry]
    setup_completed_at: Optional[str] = None
    setup_skipped_at: Optional[str] = None
    setup_progress_step: str = "welcome"


class RolesRequest(BaseModel):
    roles: List[str] = Field(..., min_length=1, max_length=_MAX_ROLES)


class CompaniesRequest(BaseModel):
    companies: List[CompanyEntry] = Field(..., min_length=1, max_length=_MAX_COMPANIES)


class MutationResponse(BaseModel):
    user_id: str
    setup_progress_step: str
    soft_warning: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_to_response(user_id: str, state: Dict[str, Any]) -> SetupStateResponse:
    return SetupStateResponse(
        user_id=user_id,
        target_roles=list(state.get("target_roles") or []),
        target_companies=[
            CompanyEntry(**c) if isinstance(c, dict) else CompanyEntry(name=str(c))
            for c in (state.get("target_companies") or [])
        ],
        setup_completed_at=state.get("setup_completed_at"),
        setup_skipped_at=state.get("setup_skipped_at"),
        setup_progress_step=state.get("setup_progress_step") or "welcome",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/setup/state", response_model=SetupStateResponse)
async def get_state(user_id: str = Depends(get_current_user)):
    store = get_profile_store()
    state = store.get_setup_state(user_id)
    return _state_to_response(user_id, state)


@router.put("/setup/roles", response_model=MutationResponse)
async def put_roles(
    payload: RolesRequest,
    user_id: str = Depends(get_current_user),
):
    cleaned = [r.strip() for r in payload.roles if r and r.strip()]
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one non-empty role required",
        )
    if len(cleaned) > _MAX_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"At most {_MAX_ROLES} roles allowed",
        )
    store = get_profile_store()
    store.update_setup_state(
        user_id,
        target_roles=cleaned,
        setup_progress_step="companies",
    )
    return MutationResponse(user_id=user_id, setup_progress_step="companies")


@router.put("/setup/companies", response_model=MutationResponse)
async def put_companies(
    payload: CompaniesRequest,
    user_id: str = Depends(get_current_user),
):
    companies: List[Dict[str, str]] = []
    for entry in payload.companies:
        name = entry.name.strip()
        if not name:
            continue
        source = entry.source.strip() if entry.source else _SOURCE_CUSTOM
        if source not in (_SOURCE_CANONICAL, _SOURCE_CUSTOM):
            source = _SOURCE_CUSTOM
        companies.append({"name": name, "source": source})

    if not companies:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one company required",
        )

    soft_warning: Optional[str] = None
    if len(companies) >= _SOFT_WARN_COMPANY_COUNT:
        soft_warning = (
            f"You added {len(companies)} companies — usually 10–25 yields better focus."
        )

    store = get_profile_store()
    store.update_setup_state(
        user_id,
        target_companies=companies,
        setup_progress_step="resume",
    )
    return MutationResponse(
        user_id=user_id,
        setup_progress_step="resume",
        soft_warning=soft_warning,
    )


@router.post("/setup/complete", response_model=MutationResponse)
async def post_complete(user_id: str = Depends(get_current_user)):
    store = get_profile_store()
    store.update_setup_state(
        user_id,
        setup_completed_at=_now_iso(),
        setup_progress_step="complete",
    )
    return MutationResponse(user_id=user_id, setup_progress_step="complete")


@router.post("/setup/skip", response_model=MutationResponse)
async def post_skip(user_id: str = Depends(get_current_user)):
    store = get_profile_store()
    store.update_setup_state(
        user_id,
        setup_skipped_at=_now_iso(),
    )
    state = store.get_setup_state(user_id)
    return MutationResponse(
        user_id=user_id,
        setup_progress_step=state.get("setup_progress_step") or "welcome",
    )
