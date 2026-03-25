"""
rag_store.py — compatibility shim.

All store logic has moved to ``scripts/stores/``.
This module re-exports everything so existing callers require no changes.

New code should import directly from the sub-modules:
    from stores import get_store, SQLiteStore, PineconeStore
    from stores import BaseStore, EmbedFn, null_embedder
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure scripts/ is on the path when run as a standalone script
_SCRIPTS = Path(__file__).parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from stores import (  # noqa: E402
    BaseStore,
    EmbedFn,
    PineconeStore,
    SQLiteStore,
    embed,
    get_store,
    null_embedder,
)
from stores.embeddings import _embed_openai, _embed_tfidf  # noqa: E402
from text_utils import profile_dict_to_text as _profile_to_text  # noqa: E402


__all__ = [
    "BaseStore",
    "EmbedFn",
    "null_embedder",
    "embed",
    "SQLiteStore",
    "PineconeStore",
    "get_store",
    # Semi-private — re-exported for backward compat
    "_embed_openai",
    "_embed_tfidf",
    "_profile_to_text",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG profile store for tailor-resume.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_store = sub.add_parser("store", help="Store a profile")
    p_store.add_argument("--profile", required=True, help="Path to profile JSON")
    p_store.add_argument("--user-id", required=True, help="Unique user identifier")

    p_query = sub.add_parser("query", help="Query stored profiles")
    p_query.add_argument("--text", required=True, help="Query text")
    p_query.add_argument("--user-id", required=True)
    p_query.add_argument("--top-k", type=int, default=3)

    sub.add_parser("list", help="List stored user IDs")

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
