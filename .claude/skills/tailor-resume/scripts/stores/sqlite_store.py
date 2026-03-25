"""
stores/sqlite_store.py
Local SQLite profile store — no API keys required.

Schema:
    profiles(id, user_id, vector_id, profile_json, embedding, stored_at)

Embedding:
    By default uses the module-level ``embed`` function from embeddings.py.
    Pass ``embed_fn`` to the constructor to inject a different embedder — this
    ensures all stored and queried vectors share the same dimension and avoids
    the BUG-1 silent-truncation issue that arises when OpenAI and TF-IDF
    dimensions differ.
"""
from __future__ import annotations

import json
import math
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional

from .base import EmbedFn
from .embeddings import embed as _default_embed

# Backward-compatible alias used by tests and internal callers
from text_utils import profile_dict_to_text as _profile_to_text


class SQLiteStore:
    def __init__(
        self,
        db_path: str = "~/.tailor_resume/profiles.db",
        embed_fn: EmbedFn = _default_embed,
    ) -> None:
        """
        Args:
            db_path:   Path to the SQLite database file (~ is expanded).
            embed_fn:  Callable that converts text to a float vector.
                       Must produce vectors of consistent dimension across
                       store() and query() calls.  Defaults to the global
                       ``embed`` function (OpenAI → TF-IDF fallback).
                       Pass ``null_embedder`` from ``stores.base`` for tests.
        """
        self._embed = embed_fn
        self._path = Path(db_path).expanduser()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                vector_id TEXT NOT NULL,
                profile_json TEXT NOT NULL,
                embedding TEXT,
                stored_at REAL NOT NULL
            )
        """)
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_user ON profiles(user_id)")
        self._conn.commit()

    def store(self, user_id: str, profile: Dict, metadata: Optional[Dict] = None) -> str:
        text = _profile_to_text(profile)
        vector = self._embed(text)
        vector_id = f"{user_id}_{int(time.time())}"
        self._conn.execute(
            "INSERT INTO profiles (user_id, vector_id, profile_json, embedding, stored_at)"
            " VALUES (?,?,?,?,?)",
            (user_id, vector_id, json.dumps(profile), json.dumps(vector), time.time()),
        )
        self._conn.commit()
        print(f"[OK] Profile stored locally (id={vector_id}).")
        return vector_id

    def query(self, user_id: str, query_text: str, top_k: int = 3) -> List[Dict]:
        q_vec = self._embed(query_text)
        rows = self._conn.execute(
            "SELECT profile_json, embedding FROM profiles"
            " WHERE user_id=? ORDER BY stored_at DESC LIMIT 50",
            (user_id,),
        ).fetchall()

        def cosine(a: List[float], b: List[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x * x for x in a)) or 1.0
            nb = math.sqrt(sum(x * x for x in b)) or 1.0
            return dot / (na * nb)

        scored = []
        for profile_json, emb_json in rows:
            if emb_json:
                score = cosine(q_vec, json.loads(emb_json))
                scored.append((score, json.loads(profile_json)))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [{"score": s, "profile": p} for s, p in scored[:top_k]]

    def delete(self, user_id: str) -> None:
        cursor = self._conn.execute(
            "DELETE FROM profiles WHERE user_id=?", (user_id,)
        )
        self._conn.commit()
        print(f"[OK] Deleted {cursor.rowcount} profiles for user '{user_id}'.")

    def list_users(self) -> List[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT user_id FROM profiles"
        ).fetchall()
        return [r[0] for r in rows]
