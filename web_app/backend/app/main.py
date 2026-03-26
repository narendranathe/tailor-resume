"""
app/main.py
FastAPI application factory for tailor-resume web backend.

Pattern mirrors autoapply-ai: create_app() returns a configured FastAPI instance.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

# Make the tailor-resume scripts importable (CLI/pipeline live there)
_SCRIPTS_DIR = Path(__file__).parent.parent.parent.parent / ".claude" / "skills" / "tailor-resume" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.API_VERSION,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
    )

    # ── CORS ────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ─────────────────────────────────────────────────────────────
    from app.routes.resume import router as resume_router
    from app.routes.profile import router as profile_router
    from app.routes.billing import router as billing_router

    app.include_router(resume_router, prefix=f"/api/{settings.API_VERSION}")
    app.include_router(profile_router, prefix=f"/api/{settings.API_VERSION}")
    app.include_router(billing_router, prefix=f"/api/{settings.API_VERSION}")

    return app


app = create_app()
