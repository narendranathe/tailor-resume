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
from typing import Any, Dict, List, Optional

from app.config import settings


_SETUP_STATE_DEFAULT: Dict[str, Any] = {
    "target_roles": [],
    "target_companies": [],
    "setup_completed_at": None,
    "setup_skipped_at": None,
    "setup_progress_step": "welcome",
}
_SETUP_STATE_KEYS = tuple(_SETUP_STATE_DEFAULT.keys())


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

    # ── Setup-wizard state (Epic #91 / M3) ─────────────────────────────────

    def get_setup_state(self, user_id: str) -> Dict[str, Any]:
        resp = (
            self._client.table(self._TABLE)
            .select(",".join(_SETUP_STATE_KEYS))
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if not resp.data:
            return dict(_SETUP_STATE_DEFAULT)
        return {k: resp.data.get(k, _SETUP_STATE_DEFAULT[k]) for k in _SETUP_STATE_KEYS}

    def update_setup_state(self, user_id: str, **fields: Any) -> None:
        payload: Dict[str, Any] = {"user_id": user_id, "updated_at": "now()"}
        for k, v in fields.items():
            if k in _SETUP_STATE_KEYS:
                payload[k] = v
        # An upsert requires the NOT NULL profile_json column; if the row
        # doesn't exist yet, seed it with an empty Profile.
        existing = self.get(user_id)
        if existing is None:
            payload["profile_json"] = {}
        self._client.table(self._TABLE).upsert(payload, on_conflict="user_id").execute()


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

        # Respect HOME env var explicitly so tests can redirect via monkeypatch.
        # Path.expanduser() ignores HOME on Windows; os.environ handles all platforms.
        _home_override = os.environ.get("HOME")
        if _home_override:
            db_path = Path(_home_override) / ".tailor_resume" / "web_profiles.db"
        else:
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
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS user_setup_state (
                user_id TEXT PRIMARY KEY,
                target_roles TEXT NOT NULL DEFAULT '[]',
                target_companies TEXT NOT NULL DEFAULT '[]',
                setup_completed_at TEXT,
                setup_skipped_at TEXT,
                setup_progress_step TEXT NOT NULL DEFAULT 'welcome',
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
        self._conn.execute("DELETE FROM user_setup_state WHERE user_id=?", (user_id,))
        self._conn.commit()

    # ── Setup-wizard state (Epic #91 / M3) ─────────────────────────────────

    def get_setup_state(self, user_id: str) -> Dict[str, Any]:
        row = self._conn.execute(
            """SELECT target_roles, target_companies, setup_completed_at,
                      setup_skipped_at, setup_progress_step
                 FROM user_setup_state WHERE user_id=?""",
            (user_id,),
        ).fetchone()
        if row is None:
            return dict(_SETUP_STATE_DEFAULT)
        return {
            "target_roles": json.loads(row[0]),
            "target_companies": json.loads(row[1]),
            "setup_completed_at": row[2],
            "setup_skipped_at": row[3],
            "setup_progress_step": row[4],
        }

    def update_setup_state(self, user_id: str, **fields: Any) -> None:
        current = self.get_setup_state(user_id)
        for k, v in fields.items():
            if k in _SETUP_STATE_KEYS:
                current[k] = v
        self._conn.execute(
            """INSERT OR REPLACE INTO user_setup_state
                 (user_id, target_roles, target_companies, setup_completed_at,
                  setup_skipped_at, setup_progress_step, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                json.dumps(current["target_roles"]),
                json.dumps(current["target_companies"]),
                current["setup_completed_at"],
                current["setup_skipped_at"],
                current["setup_progress_step"],
                time.time(),
            ),
        )
        self._conn.commit()
