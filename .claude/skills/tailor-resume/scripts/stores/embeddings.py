"""
stores/embeddings.py
Embedding utilities for converting profile text to vectors.

Backends:
    - OpenAI text-embedding-3-small (1536-dim) when OPENAI_API_KEY is set
    - TF-IDF character n-gram hashing (128-dim) as zero-dep fallback

Import rule: stdlib only — no local package imports.

NOTE: The module-level ``embed()`` function uses a global API-key check on
every call.  For predictable dimensions (critical for cosine similarity
correctness), prefer injecting an explicit EmbedFn into store constructors
rather than relying on this function.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from typing import List


def _embed_openai(text: str, api_key: str) -> List[float]:
    """Call OpenAI text-embedding-3-small (1536-dim)."""
    import urllib.error
    import urllib.request

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
    Always produces exactly ``dim`` floats.
    """
    tokens = text.lower().split()
    counts: dict = {}
    for token in tokens:
        h = int(hashlib.md5(token.encode()).hexdigest(), 16) % dim
        counts[h] = counts.get(h, 0) + 1

    vec = [counts.get(i, 0.0) for i in range(dim)]
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed(text: str) -> List[float]:
    """
    Return an embedding for *text*.

    Uses OpenAI if OPENAI_API_KEY is set; falls back to TF-IDF otherwise.

    WARNING: mixing calls when the API key changes mid-session can produce
    vectors of different dimensions, silently corrupting cosine scores.
    Use an injected EmbedFn in store constructors for predictable behaviour.
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key:
        try:
            return _embed_openai(text, api_key)
        except Exception as exc:
            print(f"[WARNING] OpenAI embedding failed ({exc}), using TF-IDF fallback.")
    return _embed_tfidf(text)
