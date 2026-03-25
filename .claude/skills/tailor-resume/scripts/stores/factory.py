"""
stores/factory.py
Environment-driven store factory.

Returns PineconeStore if PINECONE_API_KEY is set, otherwise SQLiteStore.
"""
from __future__ import annotations

import os
from typing import Union

from .pinecone_store import PineconeStore
from .sqlite_store import SQLiteStore


def get_store() -> Union[SQLiteStore, PineconeStore]:
    """Return the appropriate store based on available environment variables."""
    if os.getenv("PINECONE_API_KEY"):
        index_name = os.getenv("PINECONE_INDEX", "tailor-resume-profiles")
        print(f"[INFO] Using Pinecone backend (index: {index_name})")
        return PineconeStore(index_name=index_name)
    print("[INFO] PINECONE_API_KEY not set — using local SQLite backend.")
    return SQLiteStore()
