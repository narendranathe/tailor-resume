"""
rag_store.py
Persist and retrieve user profile embeddings for future resume tailoring sessions.

Backends supported:
    - Pinecone (cloud, preferred)
    - SQLite + JSON (local fallback, no API key needed)

Usage:
    python rag_store.py store --profile profile.json --user-id user123
    python rag_store.py query --text "data quality orchestration Airflow" --user-id user123
    python rag_store.py list --user-id user123
    python rag_store.py delete --user-id user123

Environment variables:
    PINECONE_API_KEY    — enables Pinecone backend
    PINECONE_INDEX      — index name (default: tailor-resume-profiles)
    OPENAI_API_KEY      — used for text-embedding-3-small embeddings
                          (falls back to simple TF-IDF if not set)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def _profile_to_text(profile: Dict) -> str:
    """Flatten a profile dict to searchable text."""
    parts: List[str] = []
    for role in profile.get("experience", []):
        parts.append(f"{role.get('title', '')} at {role.get('company', '')}")
        for b in role.get("bullets", []):
            parts.append(b.get("text", ""))
    for proj in profile.get("projects", []):
        parts.append(proj.get("name", ""))
        for b in proj.get("bullets", []):
            parts.append(b.get("text", ""))
    parts.extend(profile.get("skills", []))
    parts.extend(profile.get("certifications", []))
    return " ".join(parts)


def _embed_openai(text: str, api_key: str) -> List[float]:
    """Call OpenAI embedding API (text-embedding-3-small)."""
    import urllib.request
    import urllib.error

    payload = json.dumps({"model": "text-embedding-3-small", "input": text}).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/embeddings",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["data"][0]["embedding"]


def _embed_tfidf(text: str, dim: int = 128) -> List[float]:
    """
    Deterministic fallback embedding using character n-gram hashing.
    Not semantic — use only when no embedding API is available.
    """
    import math

    tokens = text.lower().split()
    counts: Dict[int, float] = {}
    for token in tokens:
        h = int(hashlib.md5(token.encode()).hexdigest(), 16) % dim
        counts[h] = counts.get(h, 0) + 1

    vec = [counts.get(i, 0.0) for i in range(dim)]
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed(text: str) -> List[float]:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key:
        try:
            return _embed_openai(text, api_key)
        except Exception as e:
            print(f"[WARNING] OpenAI embedding failed ({e}), using TF-IDF fallback.")
    return _embed_tfidf(text)


# ---------------------------------------------------------------------------
# Pinecone backend
# ---------------------------------------------------------------------------

class PineconeStore:
    def __init__(self, index_name: str = "tailor-resume-profiles"):
        try:
            from pinecone import Pinecone, ServerlessSpec  # type: ignore
        except ImportError:
            raise ImportError("Install pinecone-client: pip install pinecone-client")

        api_key = os.environ["PINECONE_API_KEY"]
        self._pc = Pinecone(api_key=api_key)
        self._index_name = index_name

        existing = [idx.name for idx in self._pc.list_indexes()]
        if index_name not in existing:
            self._pc.create_index(
                name=index_name,
                dimension=1536,  # text-embedding-3-small dim
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
        self._index = self._pc.Index(index_name)

    def store(self, user_id: str, profile: Dict, metadata: Optional[Dict] = None) -> str:
        text = _profile_to_text(profile)
        vector = embed(text)
        vector_id = f"{user_id}_{int(time.time())}"
        self._index.upsert(vectors=[{
            "id": vector_id,
            "values": vector,
            "metadata": {
                "user_id": user_id,
                "profile_json": json.dumps(profile),
                "stored_at": time.time(),
                **(metadata or {}),
            },
        }])
        return vector_id

    def query(self, user_id: str, query_text: str, top_k: int = 3) -> List[Dict]:
        vector = embed(query_text)
        results = self._index.query(
            vector=vector,
            top_k=top_k,
            filter={"user_id": user_id},
            include_metadata=True,
        )
        out = []
        for match in results.get("matches", []):
            profile = json.loads(match["metadata"].get("profile_json", "{}"))
            out.append({"score": match["score"], "profile": profile})
        return out

    def delete(self, user_id: str) -> None:
        # Pinecone doesn't support filter-based delete without fetching IDs first.
        # List all vectors for user and delete them.
        results = self._index.query(
            vector=[0.0] * 1536,
            top_k=100,
            filter={"user_id": user_id},
            include_metadata=False,
        )
        ids = [m["id"] for m in results.get("matches", [])]
        if ids:
            self._index.delete(ids=ids)
            print(f"[OK] Deleted {len(ids)} vectors for user '{user_id}'.")
        else:
            print(f"[INFO] No vectors found for user '{user_id}'.")

    def list_users(self) -> List[str]:
        # Pinecone doesn't support listing all metadata without queries.
        print("[INFO] list_users not supported for Pinecone backend without a metadata index.")
        return []


# ---------------------------------------------------------------------------
# SQLite fallback backend
# ---------------------------------------------------------------------------

class SQLiteStore:
    def __init__(self, db_path: str = "~/.tailor_resume/profiles.db"):
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
        vector = embed(text)
        vector_id = f"{user_id}_{int(time.time())}"
        self._conn.execute(
            "INSERT INTO profiles (user_id, vector_id, profile_json, embedding, stored_at) VALUES (?,?,?,?,?)",
            (user_id, vector_id, json.dumps(profile), json.dumps(vector), time.time()),
        )
        self._conn.commit()
        print(f"[OK] Profile stored locally (id={vector_id}).")
        return vector_id

    def query(self, user_id: str, query_text: str, top_k: int = 3) -> List[Dict]:
        import math

        q_vec = embed(query_text)
        rows = self._conn.execute(
            "SELECT profile_json, embedding FROM profiles WHERE user_id=? ORDER BY stored_at DESC LIMIT 50",
            (user_id,),
        ).fetchall()

        def cosine(a: List[float], b: List[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x * x for x in a)) or 1
            nb = math.sqrt(sum(x * x for x in b)) or 1
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


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_store() -> Any:
    """Return Pinecone store if API key is set, otherwise SQLite."""
    if os.getenv("PINECONE_API_KEY"):
        index_name = os.getenv("PINECONE_INDEX", "tailor-resume-profiles")
        print(f"[INFO] Using Pinecone backend (index: {index_name})")
        return PineconeStore(index_name=index_name)
    print("[INFO] PINECONE_API_KEY not set — using local SQLite backend.")
    return SQLiteStore()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="RAG profile store for tailor-resume.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_store = sub.add_parser("store", help="Store a profile")
    p_store.add_argument("--profile", required=True, help="Path to profile JSON")
    p_store.add_argument("--user-id", required=True, help="Unique user identifier")

    p_query = sub.add_parser("query", help="Query stored profiles")
    p_query.add_argument("--text", required=True, help="Query text (skills, job goals, etc.)")
    p_query.add_argument("--user-id", required=True)
    p_query.add_argument("--top-k", type=int, default=3)

    p_list = sub.add_parser("list", help="List stored user IDs")

    p_delete = sub.add_parser("delete", help="Delete all profiles for a user")
    p_delete.add_argument("--user-id", required=True)

    args = parser.parse_args()
    store = get_store()

    if args.cmd == "store":
        with open(args.profile, encoding="utf-8") as f:
            profile = json.load(f)
        vid = store.store(args.user_id, profile)
        print(f"Stored as vector_id: {vid}")

    elif args.cmd == "query":
        results = store.query(args.user_id, args.text, top_k=args.top_k)
        for i, r in enumerate(results, 1):
            print(f"\n--- Result {i} (score={r['score']:.3f}) ---")
            print(json.dumps(r["profile"], indent=2)[:500])

    elif args.cmd == "list":
        users = store.list_users()
        print("Stored user IDs:")
        for u in users:
            print(f"  {u}")

    elif args.cmd == "delete":
        store.delete(args.user_id)


if __name__ == "__main__":
    main()
