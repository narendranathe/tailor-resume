"""
stores/base.py
Shared protocol and type aliases for profile store backends.

Import rule: stdlib only — no sibling imports.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

try:
    from typing import Protocol, runtime_checkable
except ImportError:
    from typing_extensions import Protocol, runtime_checkable  # type: ignore


# ---------------------------------------------------------------------------
# Embedder type alias
# ---------------------------------------------------------------------------

#: A callable that converts a text string to a list of floats (embedding vector).
#: Injecting this into store constructors prevents the BUG-1 dimension mismatch:
#: previously ``embed()`` could store with OpenAI (1536-dim) then fall back to
#: TF-IDF (128-dim) on the next query call, silently corrupting cosine scores.
EmbedFn = Callable[[str], List[float]]


def null_embedder(text: str) -> List[float]:
    """
    Zero-dependency test embedder.

    Returns a fixed 4-dim unit vector so tests never need an API key.
    The dimension is intentionally tiny to catch any code that hard-codes
    a specific embedding dimension (e.g. the Pinecone index dimension=1536).
    """
    return [0.25, 0.25, 0.25, 0.25]


# ---------------------------------------------------------------------------
# Store protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class BaseStore(Protocol):
    """Structural protocol that both SQLiteStore and PineconeStore satisfy."""

    def store(self, user_id: str, profile: Dict, metadata: Optional[Dict] = None) -> str:
        """Persist profile for user_id. Returns a unique vector_id."""
        ...

    def query(self, user_id: str, query_text: str, top_k: int = 3) -> List[Dict]:
        """Return top_k most-similar profiles for user_id as [{score, profile}, ...]."""
        ...

    def delete(self, user_id: str) -> None:
        """Delete all stored profiles for user_id."""
        ...

    def list_users(self) -> List[str]:
        """Return list of all stored user_ids."""
        ...
