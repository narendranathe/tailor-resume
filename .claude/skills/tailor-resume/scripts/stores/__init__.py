"""
stores/__init__.py
Public API for the tailor-resume profile store package.

Backends:
    - SQLiteStore  — local SQLite, no API keys required (default)
    - PineconeStore — cloud vector DB (requires PINECONE_API_KEY)

Usage:
    from stores import get_store, SQLiteStore, PineconeStore
    from stores import BaseStore, EmbedFn, null_embedder

Injectable embedder pattern (fixes BUG-1 dimension mismatch):
    from stores import SQLiteStore, null_embedder
    store = SQLiteStore(embed_fn=null_embedder)  # zero-dependency testing
"""
from .base import BaseStore, EmbedFn, null_embedder
from .embeddings import embed
from .sqlite_store import SQLiteStore
from .pinecone_store import PineconeStore
from .factory import get_store

__all__ = [
    "BaseStore",
    "EmbedFn",
    "null_embedder",
    "embed",
    "SQLiteStore",
    "PineconeStore",
    "get_store",
]
