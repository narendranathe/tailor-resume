"""
stores/pinecone_store.py
Pinecone cloud vector store backend.

Requires:
    pip install pinecone-client
    PINECONE_API_KEY env var

Embedding:
    By default uses the module-level ``embed`` function (OpenAI → TF-IDF).
    Pass ``embed_fn`` to inject a consistent embedder — Pinecone requires that
    the index dimension matches the embedding dimension exactly.  The default
    index dimension is 1536 (text-embedding-3-small).  If you inject a custom
    embedder with a different output dimension, you must also set ``dimension``
    to match.
"""
from __future__ import annotations

import json
import os
import time
from typing import Dict, List, Optional

from .base import EmbedFn
from .embeddings import embed as _default_embed

from text_utils import profile_dict_to_text as _profile_to_text


class PineconeStore:
    def __init__(
        self,
        index_name: str = "tailor-resume-profiles",
        dimension: int = 1536,
        embed_fn: EmbedFn = _default_embed,
    ) -> None:
        """
        Args:
            index_name:  Pinecone index name.
            dimension:   Vector dimension — must match embed_fn output length.
            embed_fn:    Callable that converts text to a float vector.
        """
        try:
            from pinecone import Pinecone, ServerlessSpec  # type: ignore
        except ImportError:
            raise ImportError("Install pinecone-client: pip install pinecone-client")

        self._embed = embed_fn
        self._dimension = dimension
        api_key = os.environ["PINECONE_API_KEY"]
        self._pc = Pinecone(api_key=api_key)
        self._index_name = index_name

        existing = [idx.name for idx in self._pc.list_indexes()]
        if index_name not in existing:
            self._pc.create_index(
                name=index_name,
                dimension=dimension,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
        self._index = self._pc.Index(index_name)

    def store(self, user_id: str, profile: Dict, metadata: Optional[Dict] = None) -> str:
        text = _profile_to_text(profile)
        vector = self._embed(text)
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
        vector = self._embed(query_text)
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
        results = self._index.query(
            vector=[0.0] * self._dimension,
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
        print("[INFO] list_users not supported for Pinecone backend without a metadata index.")
        return []
