"""
app/auth.py
Clerk RS256 JWT verification — mirrors autoapply-ai auth pattern.

Extracts user_id from X-Clerk-User-Id header (set by Clerk's edge middleware)
or from the Authorization: Bearer JWT directly.

Dev fallback: if CLERK_PEM_KEY is empty, returns "dev-user" without validation.
"""
from __future__ import annotations

from fastapi import Header, HTTPException, status
from app.config import settings


async def get_current_user(
    x_clerk_user_id: str | None = Header(default=None, alias="X-Clerk-User-Id"),
    authorization: str | None = Header(default=None),
) -> str:
    """
    Return the authenticated Clerk user_id.

    Priority:
      1. X-Clerk-User-Id header (set by Clerk edge middleware — trusted in production)
      2. Authorization: Bearer <jwt> — validated with CLERK_PEM_KEY
      3. Dev fallback ("dev-user") when CLERK_PEM_KEY is not configured
    """
    # Fast path — edge middleware already verified the JWT
    if x_clerk_user_id:
        return x_clerk_user_id

    # Bearer token path
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        return _verify_clerk_jwt(token)

    # Dev fallback
    if not settings.is_production:
        return "dev-user"

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


def _verify_clerk_jwt(token: str) -> str:
    if not settings.CLERK_PEM_KEY:
        return "dev-user"
    try:
        import jwt  # PyJWT

        payload = jwt.decode(
            token,
            settings.CLERK_PEM_KEY,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        sub: str = payload.get("sub", "")
        if not sub:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token: missing sub")
        return sub
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
