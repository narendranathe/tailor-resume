"""
app/auth.py
Clerk RS256 JWT verification — mirrors autoapply-ai auth pattern.

Extracts user_id from Authorization: Bearer JWT (primary path) or from
X-Clerk-User-Id header when a valid JWT is also present (edge middleware path).

Dev fallback: if CLERK_PEM_KEY is empty AND ENVIRONMENT is development/test/local,
returns "dev-user" without validation. In production, missing CLERK_PEM_KEY raises 401.

Security fixes applied (2026-06-26):
  PATH A — X-Clerk-User-Id header now requires co-present valid JWT in production.
  PATH B — dev-user fallback gated behind explicit ENVIRONMENT check; raises 401 in prod.
  PATH C — JWT audience verification enabled when CLERK_JWT_AUDIENCE env var is set.
"""
from __future__ import annotations

import logging
import os

from fastapi import Header, HTTPException, status
from app.config import settings

logger = logging.getLogger(__name__)

# Audience verification: enabled when CLERK_JWT_AUDIENCE is set in the environment.
# Set this to your Clerk frontend API URL (e.g. https://clerk.your-domain.com) in production.
APP_AUDIENCE: str = os.getenv("CLERK_JWT_AUDIENCE", "")

# Environments where the dev-user fallback is permitted.
_DEV_ENVIRONMENTS = {"development", "test", "local"}


async def get_current_user(
    x_clerk_user_id: str | None = Header(default=None, alias="X-Clerk-User-Id"),
    authorization: str | None = Header(default=None),
) -> str:
    """
    Return the authenticated Clerk user_id.

    Priority:
      1. Authorization: Bearer <jwt> — validated with CLERK_PEM_KEY; returns sub claim.
      2. X-Clerk-User-Id header — only trusted when a valid JWT was ALSO provided and
         verified (edge middleware path). In production without a JWT, this header is
         rejected to prevent header-forging bypasses.
      3. Dev fallback ("dev-user") when CLERK_PEM_KEY is not configured AND
         ENVIRONMENT is development/test/local. Raises 401 in production.
    """
    jwt_user_id: str | None = None

    # Primary path: validate Bearer JWT
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        jwt_user_id = _verify_clerk_jwt(token)
        # JWT verified — return the sub claim directly.
        return jwt_user_id

    # PATH A fix: X-Clerk-User-Id header is only trusted without a co-present JWT
    # in dev/test/local environments with no PEM key configured. In all other cases
    # (production environment OR CLERK_PEM_KEY is set), reject the bare header.
    if x_clerk_user_id:
        if settings.is_production or settings.CLERK_PEM_KEY:
            # Production or key-configured: require a JWT — bare header is untrusted.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="X-Clerk-User-Id header requires a valid Authorization: Bearer JWT in production",
            )
        # Dev convenience: accept bare header but warn loudly.
        logger.warning(
            "Dev mode: accepting X-Clerk-User-Id header without JWT verification "
            "(CLERK_PEM_KEY is not set). Set CLERK_PEM_KEY to require JWT in production."
        )
        return x_clerk_user_id

    # PATH B fix: dev-user fallback only in non-production environments.
    if not settings.CLERK_PEM_KEY:
        if settings.ENVIRONMENT in _DEV_ENVIRONMENTS:
            logger.warning(
                "Dev mode: no credentials provided, returning 'dev-user'. "
                "ENVIRONMENT=%s, CLERK_PEM_KEY unset.",
                settings.ENVIRONMENT,
            )
            return "dev-user"
        # Production with missing key — fail closed.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


def _verify_clerk_jwt(token: str) -> str:
    """
    Validate a Clerk RS256 JWT and return the sub claim.

    PATH B fix: when CLERK_PEM_KEY is unset, only return 'dev-user' in
    development/test/local environments. Raise 401 in production.

    PATH C fix: enable audience verification when CLERK_JWT_AUDIENCE is set.
    """
    if not settings.CLERK_PEM_KEY:
        # PATH B: gate dev fallback behind explicit environment check.
        if settings.ENVIRONMENT in _DEV_ENVIRONMENTS:
            logger.warning(
                "Dev mode: CLERK_PEM_KEY not set, returning 'dev-user' without JWT validation. "
                "ENVIRONMENT=%s",
                settings.ENVIRONMENT,
            )
            return "dev-user"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated: CLERK_PEM_KEY is not configured",
        )

    try:
        import jwt  # PyJWT

        # PATH C fix: enable audience verification when APP_AUDIENCE is configured.
        decode_kwargs: dict = {
            "algorithms": ["RS256"],
            "options": {"verify_aud": bool(APP_AUDIENCE)},
        }
        if APP_AUDIENCE:
            decode_kwargs["audience"] = APP_AUDIENCE

        payload = jwt.decode(
            token,
            settings.CLERK_PEM_KEY,
            **decode_kwargs,
        )
        sub: str = payload.get("sub", "")
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing sub",
            )
        return sub
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
