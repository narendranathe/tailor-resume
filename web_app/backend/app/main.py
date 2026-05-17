"""
app/main.py
FastAPI application factory for tailor-resume web backend.

Pattern mirrors autoapply-ai: create_app() returns a configured FastAPI instance.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

# Make the tailor-resume scripts importable (CLI/pipeline live there)
_SCRIPTS_DIR = Path(__file__).parent.parent.parent.parent / ".claude" / "skills" / "tailor-resume" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# Make deploy-time utilities (readiness check) importable
_REPO_SCRIPTS_DIR = Path(__file__).parent.parent.parent.parent / "scripts"
if str(_REPO_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_REPO_SCRIPTS_DIR))

logger = logging.getLogger(__name__)


def _log_deployment_readiness() -> None:
    """Log the readiness report on startup so missing PDF deps are visible in container logs."""
    try:
        from check_deployment_readiness import check_all, critical_missing, format_report
        checks = check_all()
        missing = critical_missing(checks)
        if missing:
            # Loud warning — deployment will produce broken output until fixed.
            logger.error("Deployment readiness: %d CRITICAL dep(s) missing", len(missing))
            for c in missing:
                logger.error("  MISSING %s — %s. Fix: %s", c.package, c.impact, c.install_hint)
        else:
            logger.info(format_report(checks).splitlines()[-1])  # "PASS: all critical deps installed."
    except ImportError:
        # Don't let a missing readiness module take down the API.
        logger.warning("check_deployment_readiness module unavailable; skipping startup dep check")


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
    from app.routes.setup import router as setup_router

    app.include_router(resume_router, prefix=f"/api/{settings.API_VERSION}")
    app.include_router(profile_router, prefix=f"/api/{settings.API_VERSION}")
    app.include_router(billing_router, prefix=f"/api/{settings.API_VERSION}")
    app.include_router(setup_router, prefix=f"/api/{settings.API_VERSION}")

    # ── Startup readiness check (surfaces missing pdfminer/pypdf in logs) ──
    @app.on_event("startup")
    def _on_startup() -> None:
        _log_deployment_readiness()

    return app


app = create_app()
