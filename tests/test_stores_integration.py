"""
test_stores_integration.py

Integration tests for the ``stores/`` subtree under
``.claude/skills/tailor-resume/scripts/stores``.

Coverage strategy (issue #75, slice 2):

* ``base.py``         — direct unit tests of the ``BaseStore`` Protocol and the
                        ``null_embedder`` helper.
* ``sqlite_store.py`` — real integration tests against a fresh ``tmp_path``
                        SQLite database per test (cheap, deterministic, offline).
* ``factory.py``      — env-driven dispatch tests; the Pinecone branch uses a
                        fake ``pinecone`` module installed in ``sys.modules``.
* ``embeddings.py``   — exercises the TF-IDF fallback, the OpenAI happy path
                        (with the underlying HTTP helper monkeypatched), and the
                        OpenAI-failure → TF-IDF graceful-degradation branch.
* ``pinecone_store.py`` — exercised through a fake ``pinecone`` SDK installed in
                          ``sys.modules`` so the suite stays fully offline. A
                          single live-API guard test is gated behind
                          ``PINECONE_API_KEY``.

Notes on bugs noticed (NOT fixed here per issue #75 scope):

* ``stores/__init__.py`` eagerly imports ``PineconeStore`` which itself does
  ``from text_utils import profile_dict_to_text`` at module top.  This means
  ``import stores`` requires ``text_utils`` to be on ``sys.path`` *and* the
  module-import side effect happens whether or not Pinecone is being used.
  Conftest already handles the path; we note it here for the follow-up PR.

* ``factory.get_store()`` does NOT honour an injected ``embed_fn`` — callers
  fall back to the global ``embed()`` which can swap dimensions mid-session.
  This is the BUG-1 the docstring on ``base.EmbedFn`` explicitly warns about.
"""
from __future__ import annotations

import importlib
import os
import sys
import types
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

# Conftest already inserts the scripts dir on sys.path, so the ``stores`` package
# is importable as ``stores`` and as a submodule path.
SCRIPTS_DIR = Path(__file__).parent.parent / ".claude" / "skills" / "tailor-resume" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


SAMPLE_PROFILE: Dict[str, Any] = {
    "experience": [
        {
            "title": "Senior Data Engineer",
            "company": "DataWorks Inc",
            "start": "2022",
            "end": "Present",
            "bullets": [
                {"text": "Built governed semantic layer on Databricks"},
                {"text": "Owned CI/CD via Azure DevOps"},
            ],
        }
    ],
    "projects": [
        {
            "name": "Analytics Pipeline",
            "bullets": [{"text": "Processed 10M rows/day using Spark"}],
        }
    ],
    "skills": ["Python", "SQL", "Airflow", "Spark"],
    "certifications": ["AWS Certified Data Engineer"],
    "education": [],
    "summary": "",
}

SECOND_PROFILE: Dict[str, Any] = {
    "experience": [
        {
            "title": "ML Engineer",
            "company": "ModelCorp",
            "bullets": [{"text": "Trained ranking models with PyTorch"}],
        }
    ],
    "projects": [],
    "skills": ["PyTorch", "Ray"],
    "certifications": [],
    "education": [],
    "summary": "",
}


# ---------------------------------------------------------------------------
# Fake Pinecone SDK — installed in sys.modules so ``from pinecone import ...``
# inside PineconeStore.__init__ succeeds without a network round-trip.
# ---------------------------------------------------------------------------
class _FakeIndex:
    """In-memory stand-in for a Pinecone index."""

    def __init__(self, name: str, dimension: int) -> None:
        self.name = name
        self.dimension = dimension
        self.vectors: Dict[str, Dict[str, Any]] = {}
        self.delete_calls: List[List[str]] = []

    def upsert(self, vectors: List[Dict[str, Any]]) -> Dict[str, int]:
        for v in vectors:
            self.vectors[v["id"]] = {"values": v["values"], "metadata": v["metadata"]}
        return {"upserted_count": len(vectors)}

    def query(
        self,
        vector: List[float],
        top_k: int,
        filter: Optional[Dict[str, Any]] = None,  # noqa: A002 — match SDK kwarg
        include_metadata: bool = False,
    ) -> Dict[str, Any]:
        # naive cosine-less ranking — return matches in insertion order, filtered.
        matches = []
        for vid, payload in self.vectors.items():
            md = payload["metadata"]
            if filter:
                ok = all(md.get(k) == v for k, v in filter.items())
                if not ok:
                    continue
            entry = {"id": vid, "score": 0.99}
            if include_metadata:
                entry["metadata"] = md
            matches.append(entry)
        return {"matches": matches[:top_k]}

    def delete(self, ids: List[str]) -> None:
        self.delete_calls.append(list(ids))
        for vid in ids:
            self.vectors.pop(vid, None)


class _FakeIndexInfo:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakePinecone:
    """In-memory stand-in for the ``pinecone.Pinecone`` client."""

    instances: List["_FakePinecone"] = []

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.indexes: Dict[str, _FakeIndex] = {}
        self.create_calls: List[Dict[str, Any]] = []
        _FakePinecone.instances.append(self)

    def list_indexes(self) -> List[_FakeIndexInfo]:
        return [_FakeIndexInfo(name) for name in self.indexes]

    def create_index(self, *, name: str, dimension: int, metric: str, spec: Any) -> None:
        self.create_calls.append(
            {"name": name, "dimension": dimension, "metric": metric, "spec": spec}
        )
        self.indexes[name] = _FakeIndex(name, dimension)

    def Index(self, name: str) -> _FakeIndex:  # noqa: N802 — mirrors SDK
        return self.indexes.setdefault(name, _FakeIndex(name, dimension=1536))


class _FakeServerlessSpec:
    def __init__(self, cloud: str, region: str) -> None:
        self.cloud = cloud
        self.region = region


@pytest.fixture
def fake_pinecone(monkeypatch):
    """Install a fake ``pinecone`` module so PineconeStore can be exercised offline."""
    fake_module = types.ModuleType("pinecone")
    fake_module.Pinecone = _FakePinecone
    fake_module.ServerlessSpec = _FakeServerlessSpec
    _FakePinecone.instances.clear()
    monkeypatch.setitem(sys.modules, "pinecone", fake_module)
    monkeypatch.setenv("PINECONE_API_KEY", "fake-key-for-tests")
    yield fake_module


# ---------------------------------------------------------------------------
# base.py — null_embedder + Protocol
# ---------------------------------------------------------------------------
class TestNullEmbedder:
    def test_returns_list_of_four_floats(self):
        from stores.base import null_embedder

        vec = null_embedder("anything")
        assert isinstance(vec, list)
        assert len(vec) == 4
        assert all(isinstance(v, float) for v in vec)

    def test_is_deterministic(self):
        from stores.base import null_embedder

        assert null_embedder("a") == null_embedder("b")

    def test_unit_vector_dimension_matches_doc(self):
        from stores.base import null_embedder

        # The docstring promises a tiny fixed-dim vector specifically to catch
        # callers that hard-code 1536; lock that contract here.
        assert null_embedder("anything") == [0.25, 0.25, 0.25, 0.25]


class TestBaseStoreProtocol:
    def test_sqlite_store_satisfies_protocol(self, tmp_path):
        from stores import BaseStore, SQLiteStore
        from stores.base import null_embedder

        store = SQLiteStore(db_path=str(tmp_path / "p.db"), embed_fn=null_embedder)
        assert isinstance(store, BaseStore)

    def test_arbitrary_object_does_not_satisfy_protocol(self):
        from stores import BaseStore

        class NotAStore:
            pass

        assert not isinstance(NotAStore(), BaseStore)

    def test_minimal_implementation_satisfies_protocol(self):
        from stores import BaseStore

        class MinimalStore:
            def store(self, user_id, profile, metadata=None):
                return "vid"

            def query(self, user_id, query_text, top_k=3):
                return []

            def delete(self, user_id):
                return None

            def list_users(self):
                return []

        assert isinstance(MinimalStore(), BaseStore)


# ---------------------------------------------------------------------------
# embeddings.py
# ---------------------------------------------------------------------------
class TestEmbeddingsModule:
    def test_tfidf_default_dim_is_128(self):
        from stores.embeddings import _embed_tfidf

        assert len(_embed_tfidf("airflow spark")) == 128

    def test_tfidf_custom_dim(self):
        from stores.embeddings import _embed_tfidf

        assert len(_embed_tfidf("airflow spark", dim=64)) == 64

    def test_tfidf_is_unit_normalized(self):
        import math
        from stores.embeddings import _embed_tfidf

        vec = _embed_tfidf("airflow spark python")
        norm = math.sqrt(sum(v * v for v in vec))
        assert abs(norm - 1.0) < 1e-6

    def test_tfidf_empty_string_returns_zero_vector(self):
        from stores.embeddings import _embed_tfidf

        vec = _embed_tfidf("")
        assert len(vec) == 128
        assert all(v == 0.0 for v in vec)

    def test_tfidf_distinct_inputs_yield_distinct_vectors(self):
        from stores.embeddings import _embed_tfidf

        assert _embed_tfidf("airflow") != _embed_tfidf("pytorch")

    def test_embed_falls_back_to_tfidf_without_api_key(self, monkeypatch):
        from stores import embeddings

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        vec = embeddings.embed("data quality pipeline")
        assert len(vec) == 128

    def test_embed_uses_openai_when_api_key_set(self, monkeypatch):
        from stores import embeddings

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        captured: Dict[str, Any] = {}

        def fake_openai(text: str, api_key: str) -> List[float]:
            captured["text"] = text
            captured["api_key"] = api_key
            return [0.1] * 1536

        monkeypatch.setattr(embeddings, "_embed_openai", fake_openai)
        vec = embeddings.embed("airflow")
        assert vec == [0.1] * 1536
        assert captured == {"text": "airflow", "api_key": "sk-test"}

    def test_embed_falls_back_when_openai_raises(self, monkeypatch, capsys):
        from stores import embeddings

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        def boom(text: str, api_key: str) -> List[float]:
            raise RuntimeError("network down")

        monkeypatch.setattr(embeddings, "_embed_openai", boom)
        vec = embeddings.embed("anything")
        assert len(vec) == 128  # TF-IDF fallback dimension
        captured = capsys.readouterr().out
        assert "WARNING" in captured

    def test_embed_openai_request_shape(self, monkeypatch):
        """Cover the urllib branch of _embed_openai without hitting the network."""
        from stores import embeddings

        class _FakeResp:
            def __init__(self, payload: bytes) -> None:
                self._payload = payload

            def read(self) -> bytes:
                return self._payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        captured: Dict[str, Any] = {}

        def fake_urlopen(req, timeout):
            captured["url"] = req.full_url
            captured["data"] = req.data
            captured["headers"] = dict(req.header_items())
            return _FakeResp(b'{"data":[{"embedding":[0.5,0.5,0.5]}]}')

        # Patch the underlying urlopen the helper imports at call time.
        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

        out = embeddings._embed_openai("hello", api_key="sk-test")
        assert out == [0.5, 0.5, 0.5]
        assert captured["url"] == "https://api.openai.com/v1/embeddings"
        assert b"text-embedding-3-small" in captured["data"]
        assert captured["headers"]["Authorization"] == "Bearer sk-test"


# ---------------------------------------------------------------------------
# sqlite_store.py — real DB integration
# ---------------------------------------------------------------------------
class TestSQLiteStoreIntegration:
    @pytest.fixture
    def store(self, tmp_path):
        from stores import SQLiteStore
        from stores.base import null_embedder

        return SQLiteStore(db_path=str(tmp_path / "profiles.db"), embed_fn=null_embedder)

    def test_init_creates_db_file(self, tmp_path):
        from stores import SQLiteStore
        from stores.base import null_embedder

        db_path = tmp_path / "fresh.db"
        SQLiteStore(db_path=str(db_path), embed_fn=null_embedder)
        assert db_path.exists()

    def test_init_creates_parent_directory(self, tmp_path):
        from stores import SQLiteStore
        from stores.base import null_embedder

        nested = tmp_path / "nested" / "deep" / "p.db"
        SQLiteStore(db_path=str(nested), embed_fn=null_embedder)
        assert nested.exists()

    def test_init_expands_tilde(self, tmp_path, monkeypatch):
        from stores import SQLiteStore
        from stores.base import null_embedder

        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Windows
        store = SQLiteStore(db_path="~/expanded/p.db", embed_fn=null_embedder)
        assert (tmp_path / "expanded" / "p.db").exists()
        store._conn.close()

    def test_store_returns_unique_vector_id_with_user_prefix(self, store):
        vid = store.store("alice", SAMPLE_PROFILE)
        assert isinstance(vid, str)
        assert vid.startswith("alice_")

    def test_store_persists_profile_round_trip(self, store):
        store.store("alice", SAMPLE_PROFILE)
        results = store.query("alice", "anything")
        assert len(results) == 1
        assert results[0]["profile"]["experience"][0]["title"] == "Senior Data Engineer"

    def test_query_returns_score_and_profile_keys(self, store):
        store.store("alice", SAMPLE_PROFILE)
        results = store.query("alice", "anything")
        assert set(results[0].keys()) == {"score", "profile"}

    def test_query_unknown_user_returns_empty_list(self, store):
        assert store.query("nobody", "anything") == []

    def test_query_respects_top_k(self, store):
        for _ in range(5):
            store.store("alice", SAMPLE_PROFILE)
        assert len(store.query("alice", "anything", top_k=2)) == 2

    def test_query_isolates_users(self, store):
        store.store("alice", SAMPLE_PROFILE)
        store.store("bob", SECOND_PROFILE)
        alice_hits = store.query("alice", "anything")
        bob_hits = store.query("bob", "anything")
        assert len(alice_hits) == 1
        assert len(bob_hits) == 1
        assert alice_hits[0]["profile"]["experience"][0]["company"] == "DataWorks Inc"
        assert bob_hits[0]["profile"]["experience"][0]["company"] == "ModelCorp"

    def test_query_orders_by_cosine_score_descending(self, tmp_path):
        from stores import SQLiteStore

        # Inject deterministic embedders that produce distinct vectors so we can
        # verify the cosine ordering.
        def stable_embed(text: str) -> List[float]:
            # Map content keyword to a one-hot vector for a tiny vocabulary.
            vocab = ["airflow", "pytorch", "spark"]
            return [1.0 if w in text.lower() else 0.0 for w in vocab]

        store = SQLiteStore(db_path=str(tmp_path / "p.db"), embed_fn=stable_embed)
        store.store("alice", {"skills": ["airflow"]})
        store.store("alice", {"skills": ["pytorch"]})
        store.store("alice", {"skills": ["spark"]})

        results = store.query("alice", "airflow", top_k=3)
        # The "airflow" profile must be ranked first; the other two have score 0.
        assert results[0]["profile"]["skills"] == ["airflow"]
        assert results[0]["score"] >= results[-1]["score"]

    def test_query_skips_rows_with_no_embedding(self, store):
        # Insert a malformed row directly to exercise the ``if emb_json`` branch.
        store._conn.execute(
            "INSERT INTO profiles (user_id, vector_id, profile_json, embedding, stored_at)"
            " VALUES (?,?,?,?,?)",
            ("alice", "alice_x", "{}", None, 0.0),
        )
        store._conn.commit()
        # No embedding rows present yet → query must not crash and return [].
        assert store.query("alice", "anything") == []

    def test_list_users_returns_distinct_users(self, store):
        store.store("alice", SAMPLE_PROFILE)
        store.store("alice", SAMPLE_PROFILE)
        store.store("bob", SECOND_PROFILE)
        users = sorted(store.list_users())
        assert users == ["alice", "bob"]

    def test_list_users_empty_initially(self, store):
        assert store.list_users() == []

    def test_delete_removes_only_target_user(self, store):
        store.store("alice", SAMPLE_PROFILE)
        store.store("bob", SECOND_PROFILE)
        store.delete("alice")
        users = store.list_users()
        assert users == ["bob"]

    def test_delete_unknown_user_is_noop(self, store):
        store.delete("ghost")  # must not raise
        assert store.list_users() == []

    def test_default_embedder_is_module_embed(self, tmp_path, monkeypatch):
        """Constructor without embed_fn falls through to the global embed()."""
        from stores import SQLiteStore

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        store = SQLiteStore(db_path=str(tmp_path / "default.db"))
        store.store("u", {"skills": ["python"]})
        assert store.query("u", "python")  # cosine of TF-IDF should be > 0


# ---------------------------------------------------------------------------
# factory.py
# ---------------------------------------------------------------------------
class TestFactory:
    def test_returns_sqlite_when_pinecone_key_absent(self, monkeypatch, tmp_path):
        from stores import SQLiteStore, get_store

        monkeypatch.delenv("PINECONE_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        # Redirect home so the default ~/.tailor_resume path is sandboxed.
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        store = get_store()
        assert isinstance(store, SQLiteStore)

    def test_returns_pinecone_when_key_present(self, monkeypatch, fake_pinecone, capsys):
        from stores import PineconeStore, get_store

        monkeypatch.setenv("PINECONE_INDEX", "custom-index-name")
        store = get_store()
        assert isinstance(store, PineconeStore)
        out = capsys.readouterr().out
        assert "custom-index-name" in out

    def test_falls_back_to_default_index_name(self, monkeypatch, fake_pinecone):
        from stores import PineconeStore, get_store

        monkeypatch.delenv("PINECONE_INDEX", raising=False)
        store = get_store()
        assert isinstance(store, PineconeStore)
        # Default index name from the factory.
        assert store._index_name == "tailor-resume-profiles"

    def test_factory_emits_info_message_when_using_sqlite(self, monkeypatch, capsys, tmp_path):
        from stores import get_store

        monkeypatch.delenv("PINECONE_API_KEY", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        get_store()
        out = capsys.readouterr().out
        assert "SQLite" in out


# ---------------------------------------------------------------------------
# pinecone_store.py — exercised against a fake in-memory SDK
# ---------------------------------------------------------------------------
class TestPineconeStoreFakeBackend:
    def test_init_creates_index_when_missing(self, fake_pinecone):
        from stores import PineconeStore
        from stores.base import null_embedder

        PineconeStore(index_name="new-index", dimension=4, embed_fn=null_embedder)
        client = _FakePinecone.instances[-1]
        assert client.create_calls
        assert client.create_calls[0]["name"] == "new-index"
        assert client.create_calls[0]["dimension"] == 4
        assert client.create_calls[0]["metric"] == "cosine"

    def test_init_skips_create_when_index_exists(self, monkeypatch):
        # Pre-seed a fake Pinecone module whose client already has the index, so
        # the constructor takes the "skip create_index" branch.
        from stores.base import null_embedder

        class _PreseededPinecone(_FakePinecone):
            def __init__(self, api_key: str) -> None:
                super().__init__(api_key)
                self.indexes["already-here"] = _FakeIndex("already-here", dimension=4)

        fake_module = types.ModuleType("pinecone")
        fake_module.Pinecone = _PreseededPinecone
        fake_module.ServerlessSpec = _FakeServerlessSpec
        _FakePinecone.instances.clear()
        monkeypatch.setitem(sys.modules, "pinecone", fake_module)
        monkeypatch.setenv("PINECONE_API_KEY", "fake")

        from stores import PineconeStore

        PineconeStore(index_name="already-here", dimension=4, embed_fn=null_embedder)
        client = _FakePinecone.instances[-1]
        assert client.create_calls == []  # branch verified: no create call

    def test_store_upserts_vector_with_metadata(self, fake_pinecone):
        from stores import PineconeStore
        from stores.base import null_embedder

        store = PineconeStore(index_name="t", dimension=4, embed_fn=null_embedder)
        vid = store.store("alice", SAMPLE_PROFILE, metadata={"source": "linkedin"})
        client = _FakePinecone.instances[-1]
        index = client.indexes["t"]
        assert vid in index.vectors
        md = index.vectors[vid]["metadata"]
        assert md["user_id"] == "alice"
        assert md["source"] == "linkedin"
        assert "profile_json" in md
        assert index.vectors[vid]["values"] == [0.25, 0.25, 0.25, 0.25]

    def test_store_returns_vector_id_with_user_prefix(self, fake_pinecone):
        from stores import PineconeStore
        from stores.base import null_embedder

        store = PineconeStore(index_name="t", dimension=4, embed_fn=null_embedder)
        vid = store.store("bob", SECOND_PROFILE)
        assert vid.startswith("bob_")

    def test_query_returns_filtered_results(self, fake_pinecone):
        from stores import PineconeStore
        from stores.base import null_embedder

        store = PineconeStore(index_name="t", dimension=4, embed_fn=null_embedder)
        store.store("alice", SAMPLE_PROFILE)
        store.store("bob", SECOND_PROFILE)
        results = store.query("alice", "anything", top_k=5)
        assert len(results) == 1
        assert results[0]["profile"]["experience"][0]["company"] == "DataWorks Inc"
        assert "score" in results[0]

    def test_query_returns_empty_when_no_matches(self, fake_pinecone):
        from stores import PineconeStore
        from stores.base import null_embedder

        store = PineconeStore(index_name="t", dimension=4, embed_fn=null_embedder)
        assert store.query("ghost", "anything") == []

    def test_delete_removes_user_vectors(self, fake_pinecone, capsys):
        from stores import PineconeStore
        from stores.base import null_embedder

        store = PineconeStore(index_name="t", dimension=4, embed_fn=null_embedder)
        store.store("alice", SAMPLE_PROFILE)
        store.delete("alice")
        client = _FakePinecone.instances[-1]
        index = client.indexes["t"]
        assert index.delete_calls  # delete invoked at least once
        assert not any(md["metadata"]["user_id"] == "alice" for md in index.vectors.values())
        out = capsys.readouterr().out
        assert "Deleted" in out

    def test_delete_logs_when_no_matches(self, fake_pinecone, capsys):
        from stores import PineconeStore
        from stores.base import null_embedder

        store = PineconeStore(index_name="t", dimension=4, embed_fn=null_embedder)
        store.delete("ghost")
        out = capsys.readouterr().out
        assert "No vectors" in out

    def test_list_users_returns_empty_with_warning(self, fake_pinecone, capsys):
        from stores import PineconeStore
        from stores.base import null_embedder

        store = PineconeStore(index_name="t", dimension=4, embed_fn=null_embedder)
        assert store.list_users() == []
        out = capsys.readouterr().out
        assert "not supported" in out

    def test_uses_default_embedder_when_none_injected(self, fake_pinecone, monkeypatch):
        """Default embed_fn is the module-level embed; verify it is wired."""
        from stores import PineconeStore

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        # Use the module's default 1536 dim — TF-IDF gives 128, so we override
        # the dimension to match the default embedder's actual output length.
        store = PineconeStore(index_name="default", dimension=1536)
        # Verify _embed is a callable that returns a list of floats.
        out = store._embed("hello")
        assert isinstance(out, list)
        assert all(isinstance(v, float) for v in out)


class TestPineconeStoreImportError:
    def test_constructor_raises_when_pinecone_missing(self, monkeypatch):
        # Force ``from pinecone import ...`` inside __init__ to fail.
        monkeypatch.setenv("PINECONE_API_KEY", "fake")
        # Ensure pinecone is absent — temporarily set it to None and remove
        # any cached submodule so ``import pinecone`` re-runs and fails.
        monkeypatch.setitem(sys.modules, "pinecone", None)

        from stores import PineconeStore

        with pytest.raises(ImportError, match="pinecone-client"):
            PineconeStore(index_name="x", dimension=4)


# ---------------------------------------------------------------------------
# Live Pinecone smoke test (skipped unless PINECONE_API_KEY is genuinely set
# in the environment AND the user opts in via TAILOR_RESUME_LIVE_PINECONE=1).
# This belongs in CI nightly, not in PR validation.
# ---------------------------------------------------------------------------
@pytest.mark.skipif(
    not (os.getenv("PINECONE_API_KEY") and os.getenv("TAILOR_RESUME_LIVE_PINECONE") == "1"),
    reason="Live Pinecone smoke test requires PINECONE_API_KEY + TAILOR_RESUME_LIVE_PINECONE=1.",
)
class TestPineconeStoreLive:  # pragma: no cover — gated, not run in CI
    def test_round_trip(self):
        from stores import PineconeStore

        store = PineconeStore(index_name="tailor-resume-tests")
        vid = store.store("test-user", SAMPLE_PROFILE)
        assert vid
        store.delete("test-user")
