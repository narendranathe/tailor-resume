"""
app/db/supabase.py
Supabase client wrapper for profile persistence.

Falls back to SQLiteStore if SUPABASE_URL / SUPABASE_SERVICE_KEY are not set.
All callers go through get_profile_store() — they never instantiate the store directly.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

from app.config import settings


# ---------------------------------------------------------------------------
# Supabase profile store — wraps postgrest via supabase-py
# ---------------------------------------------------------------------------

class SupabaseProfileStore:
    """Stores parsed Profile JSON in Supabase user_profiles table."""

    _TABLE = "user_profiles"

    def __init__(self) -> None:
        try:
            from supabase import create_client  # type: ignore
        except ImportError:
            raise ImportError("pip install supabase")
        self._client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)

    def upsert(self, user_id: str, profile: Dict) -> None:
        self._client.table(self._TABLE).upsert({
            "user_id": user_id,
            "profile_json": profile,
            "updated_at": "now()",
        }, on_conflict="user_id").execute()

    def get(self, user_id: str) -> Optional[Dict]:
        resp = (
            self._client.table(self._TABLE)
            .select("profile_json")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if resp.data:
            return resp.data["profile_json"]
        return None

    def delete(self, user_id: str) -> None:
        self._client.table(self._TABLE).delete().eq("user_id", user_id).execute()


# ---------------------------------------------------------------------------
# Factory — returns the right store based on env vars
# ---------------------------------------------------------------------------

def get_profile_store():
    """
    Return the best available profile store.

    Priority:
        1. SupabaseProfileStore  — if SUPABASE_URL + SUPABASE_SERVICE_KEY set
        2. SQLiteProfileStore    — local fallback, no API keys required
    """
    if settings.has_supabase:
        return SupabaseProfileStore()
    return _SQLiteProfileStore()


class _SQLiteProfileStore:
    """Minimal SQLite-backed profile store for local dev / fallback."""

    def __init__(self) -> None:
        import sqlite3
        from pathlib import Path

        db_path = Path("~/.tailor_resume/web_profiles.db").expanduser()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                profile_json TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        self._conn.commit()

    def upsert(self, user_id: str, profile: Dict) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO user_profiles (user_id, profile_json, updated_at) VALUES (?,?,?)",
            (user_id, json.dumps(profile), time.time()),
        )
        self._conn.commit()

    def get(self, user_id: str) -> Optional[Dict]:
        row = self._conn.execute(
            "SELECT profile_json FROM user_profiles WHERE user_id=?", (user_id,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def delete(self, user_id: str) -> None:
        self._conn.execute("DELETE FROM user_profiles WHERE user_id=?", (user_id,))
        self._conn.commit()
