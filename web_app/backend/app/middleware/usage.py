"""
app/middleware/usage.py
Usage metering middleware — enforces Free tier limit (5 tailors/month).
Checked before each POST /resume/tailor call.
Skipped if user has plan=pro in Supabase user_profiles.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, status

from app.config import settings

# Free tier monthly limit
FREE_LIMIT = 5


def _current_month() -> str:
    """Return the current month key in YYYY-MM format."""
    return datetime.utcnow().strftime("%Y-%m")


# ---------------------------------------------------------------------------
# Supabase-backed usage store
# ---------------------------------------------------------------------------

class _SupabaseUsageStore:
    """Usage store backed by Supabase usage table and user_profiles.plan column."""

    def __init__(self) -> None:
        from supabase import create_client  # type: ignore
        self._client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)

    def get_plan(self, user_id: str) -> str:
        resp = (
            self._client.table("user_profiles")
            .select("plan")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if resp.data:
            return resp.data.get("plan", "free")
        return "free"

    def get_count(self, user_id: str, month: str) -> int:
        resp = (
            self._client.table("usage")
            .select("resume_count")
            .eq("user_id", user_id)
            .eq("month", month)
            .maybe_single()
            .execute()
        )
        if resp.data:
            return resp.data.get("resume_count", 0)
        return 0

    def increment(self, user_id: str, month: str) -> None:
        current = self.get_count(user_id, month)
        self._client.table("usage").upsert(
            {
                "user_id": user_id,
                "month": month,
                "resume_count": current + 1,
            },
            on_conflict="user_id,month",
        ).execute()

    def set_plan(self, user_id: str, plan: str, stripe_customer_id: Optional[str] = None) -> None:
        data: dict = {"user_id": user_id, "plan": plan}
        if stripe_customer_id is not None:
            data["stripe_customer_id"] = stripe_customer_id
        self._client.table("user_profiles").upsert(data, on_conflict="user_id").execute()


# ---------------------------------------------------------------------------
# SQLite fallback usage store
# ---------------------------------------------------------------------------

class _SQLiteUsageStore:
    """Local SQLite-backed usage store for dev / fallback when Supabase is not configured."""

    def __init__(self) -> None:
        db_path = Path("~/.tailor_resume/usage.db").expanduser()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS usage (
                user_id TEXT NOT NULL,
                month TEXT NOT NULL,
                resume_count INT NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, month)
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS user_plans (
                user_id TEXT PRIMARY KEY,
                plan TEXT NOT NULL DEFAULT 'free',
                stripe_customer_id TEXT
            )
        """)
        self._conn.commit()

    def get_plan(self, user_id: str) -> str:
        row = self._conn.execute(
            "SELECT plan FROM user_plans WHERE user_id=?", (user_id,)
        ).fetchone()
        return row[0] if row else "free"

    def get_count(self, user_id: str, month: str) -> int:
        row = self._conn.execute(
            "SELECT resume_count FROM usage WHERE user_id=? AND month=?", (user_id, month)
        ).fetchone()
        return row[0] if row else 0

    def increment(self, user_id: str, month: str) -> None:
        self._conn.execute(
            """
            INSERT INTO usage (user_id, month, resume_count)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, month) DO UPDATE SET resume_count = resume_count + 1
            """,
            (user_id, month),
        )
        self._conn.commit()

    def set_plan(self, user_id: str, plan: str, stripe_customer_id: Optional[str] = None) -> None:
        self._conn.execute(
            """
            INSERT INTO user_plans (user_id, plan, stripe_customer_id)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET plan=excluded.plan,
                stripe_customer_id=COALESCE(excluded.stripe_customer_id, stripe_customer_id)
            """,
            (user_id, plan, stripe_customer_id),
        )
        self._conn.commit()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def _get_usage_store():
    if settings.has_supabase:
        return _SupabaseUsageStore()
    return _SQLiteUsageStore()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_usage(user_id: str) -> None:
    """
    Raise HTTPException 402 if the user is on the free plan and has reached the monthly limit.
    No-op for pro users.
    """
    store = _get_usage_store()
    plan = store.get_plan(user_id)
    if plan == "pro":
        return

    month = _current_month()
    count = store.get_count(user_id, month)
    if count >= FREE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Free tier limit reached ({FREE_LIMIT} tailored resumes/month). "
                "Upgrade to Pro for unlimited access."
            ),
        )


def increment_usage(user_id: str) -> None:
    """Increment the tailor count for the current month."""
    store = _get_usage_store()
    month = _current_month()
    store.increment(user_id, month)


def get_usage_info(user_id: str) -> dict:
    """Return {plan, count_this_month, limit} for the given user."""
    store = _get_usage_store()
    plan = store.get_plan(user_id)
    month = _current_month()
    count = store.get_count(user_id, month)
    limit = None if plan == "pro" else FREE_LIMIT
    return {"plan": plan, "count_this_month": count, "limit": limit}


def set_user_plan(user_id: str, plan: str, stripe_customer_id: Optional[str] = None) -> None:
    """Set a user's plan (called from billing webhook)."""
    store = _get_usage_store()
    store.set_plan(user_id, plan, stripe_customer_id)
