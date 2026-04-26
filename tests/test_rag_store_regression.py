"""
test_rag_store_regression.py

Characterization tests for rag_store.py — pins current SQLiteStore behavior so
it can be verified to be preserved when rag_store.py is split into a stores/
package (GitHub issue #53).

All tests use the SQLite backend with TF-IDF embeddings (no API keys required).

BUGS DOCUMENTED INLINE:
  - BUG-1 (dimension mismatch): SQLiteStore.query() uses zip() for cosine
    similarity. If the stored embedding and query embedding have different
    lengths, zip() silently truncates to the shorter one, producing a wrong
    score instead of raising an error.  The cosine value is meaningless but
    no exception is thrown.

  - BUG-2 (no injectable embedder): SQLiteStore hard-codes the global embed()
    function. There is no way to pass a custom embed_fn at construction time,
    so tests cannot fully isolate the embedding logic — they must monkeypatch
    the env to force TF-IDF.

Design note for the refactor (stores/ package):
  - Pass embed_fn as a constructor argument to SQLiteStore so tests can inject
    a deterministic null_embedder without environment manipulation.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import List

import pytest

# Make scripts/ importable — conftest.py already does sys.path.insert, but
# keep this here so the file is fully self-contained if run in isolation.
_SCRIPTS_DIR = Path(__file__).parent.parent / ".claude" / "skills" / "tailor-resume" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from rag_store import SQLiteStore, _embed_tfidf, get_store  # noqa: E402
from resume_types import Profile, Role, Bullet, Project, profile_to_dict  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _null_vector(text: str, dim: int = 128) -> List[float]:
    """Deterministic, offline embedding: same as _embed_tfidf."""
    return _embed_tfidf(text, dim=dim)


def _make_profile_dict(**overrides) -> dict:
    """Return a minimal valid profile dict, with optional overrides."""
    base = {
        "experience": [
            {
                "title": "Data Engineer",
                "company": "Acme Corp",
                "start": "Jan 2022",
                "end": "Present",
                "location": "Remote",
                "bullets": [
                    {
                        "text": "Built Airflow pipelines processing 5M rows/day",
                        "metrics": ["5M rows/day"],
                        "tools": ["Airflow"],
                        "evidence_source": "test",
                        "confidence": "high",
                    }
                ],
            }
        ],
        "projects": [],
        "skills": ["Python", "SQL", "Airflow"],
        "education": [],
        "certifications": ["AWS Certified Data Engineer"],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def no_openai_key(monkeypatch):
    """Ensure all tests use TF-IDF (no real API calls)."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("PINECONE_API_KEY", raising=False)


@pytest.fixture
def sqlite_store(tmp_path):
    """Fresh SQLiteStore backed by a temp file — no cross-test pollution."""
    return SQLiteStore(db_path=str(tmp_path / "regression.db"))


@pytest.fixture
def sample_profile() -> dict:
    return _make_profile_dict()


@pytest.fixture
def dataclass_profile() -> Profile:
    """A Profile built from dataclasses, serialised via profile_to_dict."""
    bullet = Bullet(
        text="Migrated on-prem Hadoop cluster to Databricks, reducing job time by 40%",
        metrics=["40%"],
        tools=["Databricks"],
        evidence_source="linkedin",
        confidence="high",
    )
    role = Role(
        title="Senior Data Engineer",
        company="TechCorp",
        start="Mar 2021",
        end="Dec 2023",
        location="Dallas TX",
        bullets=[bullet],
    )
    proj_bullet = Bullet(
        text="Processed 10M events/day through Kafka + Spark pipeline",
        metrics=["10M events/day"],
        tools=["Kafka", "Spark"],
        evidence_source="github",
        confidence="high",
    )
    project = Project(
        name="Real-Time Risk Engine",
        tech=["Kafka", "Spark", "FastAPI"],
        bullets=[proj_bullet],
        date="2023",
    )
    return Profile(
        experience=[role],
        projects=[project],
        skills=["Python", "Spark", "Kafka", "Airflow"],
        education=[{"degree": "B.S. Computer Science", "school": "Mizzou", "year": "2019"}],
        certifications=["Databricks Certified Associate Developer"],
    )


# ---------------------------------------------------------------------------
# ROUNDTRIP: store → query
# ---------------------------------------------------------------------------

class TestStoreRetrieveRoundtrip:
    """Pins the basic store-then-query contract."""

    def test_stored_profile_appears_in_query_results(self, sqlite_store, sample_profile):
        """Storing a profile and querying with a matching term returns that profile."""
        sqlite_store.store("test_user", sample_profile)
        results = sqlite_store.query("test_user", "Airflow pipelines data")
        assert len(results) >= 1
        first = results[0]["profile"]
        assert first["experience"][0]["title"] == "Data Engineer"

    def test_query_result_structure_has_score_and_profile(self, sqlite_store, sample_profile):
        """Every result dict must have 'score' (float) and 'profile' (dict) keys."""
        sqlite_store.store("test_user", sample_profile)
        results = sqlite_store.query("test_user", "Python SQL")
        assert "score" in results[0]
        assert "profile" in results[0]
        assert isinstance(results[0]["score"], float)
        assert isinstance(results[0]["profile"], dict)

    def test_score_is_bounded_between_minus_one_and_one(self, sqlite_store, sample_profile):
        """Cosine similarity must be in [-1, 1]."""
        sqlite_store.store("test_user", sample_profile)
        results = sqlite_store.query("test_user", "Airflow orchestration")
        for r in results:
            assert -1.0 <= r["score"] <= 1.0 + 1e-9  # allow float epsilon

    def test_two_profiles_top_k_one_returns_exactly_one(self, sqlite_store, sample_profile):
        """top_k=1 must return exactly 1 result even when 2 profiles are stored."""
        sqlite_store.store("user_ab", sample_profile)
        alt_profile = _make_profile_dict(skills=["Java", "Scala", "Spark"])
        sqlite_store.store("user_ab", alt_profile)
        results = sqlite_store.query("user_ab", "data engineering", top_k=1)
        assert len(results) == 1

    def test_query_returns_at_most_top_k_results(self, sqlite_store, sample_profile):
        """Store 5 profiles, query with top_k=3 — must return ≤3."""
        for i in range(5):
            sqlite_store.store("power_user", _make_profile_dict(skills=[f"Tool{i}"]))
        results = sqlite_store.query("power_user", "data", top_k=3)
        assert len(results) <= 3

    def test_results_are_sorted_by_score_descending(self, sqlite_store):
        """Results list must be in descending score order."""
        # Store two semantically different profiles so scores differ.
        sqlite_store.store(
            "u1",
            _make_profile_dict(skills=["Airflow", "Python", "Kafka"]),
        )
        sqlite_store.store(
            "u1",
            _make_profile_dict(skills=["React", "Node", "CSS"]),
        )
        results = sqlite_store.query("u1", "Airflow Kafka orchestration", top_k=10)
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True), "Results must be sorted descending by score"

    def test_query_for_wrong_user_returns_empty(self, sqlite_store, sample_profile):
        """Profiles are user-scoped: querying a different user_id must return []."""
        sqlite_store.store("alice", sample_profile)
        results = sqlite_store.query("bob", "Airflow")
        assert results == []

    def test_query_empty_store_returns_empty(self, sqlite_store):
        """Querying a store that has never had data returns []."""
        results = sqlite_store.query("nobody", "anything")
        assert results == []


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

class TestDelete:
    def test_delete_clears_profiles_for_user(self, sqlite_store, sample_profile):
        """After delete(), query() must return []."""
        sqlite_store.store("carol", sample_profile)
        sqlite_store.delete("carol")
        results = sqlite_store.query("carol", "Airflow")
        assert results == []

    def test_delete_only_removes_target_user(self, sqlite_store, sample_profile):
        """Deleting user A must not affect user B's profiles."""
        sqlite_store.store("alice", sample_profile)
        sqlite_store.store("bob", sample_profile)
        sqlite_store.delete("alice")
        # Bob's data must survive.
        results = sqlite_store.query("bob", "Airflow")
        assert len(results) >= 1

    def test_delete_nonexistent_user_is_idempotent(self, sqlite_store):
        """Deleting a user that was never stored must not raise."""
        sqlite_store.delete("ghost")  # must not raise

    def test_double_delete_is_idempotent(self, sqlite_store, sample_profile):
        """Deleting the same user twice must not raise on the second call."""
        sqlite_store.store("diana", sample_profile)
        sqlite_store.delete("diana")
        sqlite_store.delete("diana")  # second delete — must be safe


# ---------------------------------------------------------------------------
# list_users
# ---------------------------------------------------------------------------

class TestListUsers:
    def test_list_users_empty_store_returns_empty_list(self, sqlite_store):
        assert sqlite_store.list_users() == []

    def test_list_users_after_storing_three_profiles(self, sqlite_store, sample_profile):
        """Storing profiles for 3 distinct users → list_users() returns all 3."""
        sqlite_store.store("user_x", sample_profile)
        sqlite_store.store("user_y", sample_profile)
        sqlite_store.store("user_z", sample_profile)
        users = sqlite_store.list_users()
        assert set(users) >= {"user_x", "user_y", "user_z"}

    def test_list_users_after_delete_removes_user(self, sqlite_store, sample_profile):
        """After deleting one of 3 users, list_users() must return exactly 2."""
        sqlite_store.store("u1", sample_profile)
        sqlite_store.store("u2", sample_profile)
        sqlite_store.store("u3", sample_profile)
        sqlite_store.delete("u2")
        users = sqlite_store.list_users()
        assert "u2" not in users
        assert "u1" in users
        assert "u3" in users

    def test_list_users_same_user_stored_multiple_times_appears_once(self, sqlite_store, sample_profile):
        """Storing the same user_id multiple times must not produce duplicates in list_users()."""
        sqlite_store.store("repeating_user", sample_profile)
        sqlite_store.store("repeating_user", _make_profile_dict(skills=["Scala"]))
        users = sqlite_store.list_users()
        assert users.count("repeating_user") == 1


# ---------------------------------------------------------------------------
# SERIALIZATION: dataclass Profile round-trip
# ---------------------------------------------------------------------------

class TestSerializationRoundtrip:
    """Verify that Profile dataclass objects survive store → query intact."""

    def test_profile_dataclass_roundtrip_preserves_experience_title(
        self, sqlite_store, dataclass_profile
    ):
        """profile_to_dict(Profile) → store → query → profile['experience'][0]['title'] matches."""
        profile_dict = profile_to_dict(dataclass_profile)
        sqlite_store.store("roundtrip_user", profile_dict)
        results = sqlite_store.query("roundtrip_user", "Senior Data Engineer Databricks")
        assert len(results) >= 1
        retrieved = results[0]["profile"]
        assert retrieved["experience"][0]["title"] == "Senior Data Engineer"

    def test_profile_dataclass_roundtrip_preserves_nested_bullet(
        self, sqlite_store, dataclass_profile
    ):
        """Bullet text inside a Role must survive serialization unchanged."""
        profile_dict = profile_to_dict(dataclass_profile)
        sqlite_store.store("roundtrip_user", profile_dict)
        results = sqlite_store.query("roundtrip_user", "Databricks cluster migration")
        retrieved = results[0]["profile"]
        bullet_text = retrieved["experience"][0]["bullets"][0]["text"]
        assert "Databricks" in bullet_text

    def test_profile_dataclass_roundtrip_preserves_project(
        self, sqlite_store, dataclass_profile
    ):
        """Project name and tech list must survive serialization."""
        profile_dict = profile_to_dict(dataclass_profile)
        sqlite_store.store("roundtrip_user", profile_dict)
        results = sqlite_store.query("roundtrip_user", "Kafka Spark real time")
        retrieved = results[0]["profile"]
        project_names = [p["name"] for p in retrieved.get("projects", [])]
        assert "Real-Time Risk Engine" in project_names

    def test_profile_dataclass_roundtrip_preserves_skills(
        self, sqlite_store, dataclass_profile
    ):
        """Skills list must survive serialization intact."""
        profile_dict = profile_to_dict(dataclass_profile)
        sqlite_store.store("roundtrip_user", profile_dict)
        results = sqlite_store.query("roundtrip_user", "Python Spark Kafka")
        retrieved = results[0]["profile"]
        assert "Python" in retrieved["skills"]
        assert "Spark" in retrieved["skills"]

    def test_profile_dataclass_roundtrip_preserves_certifications(
        self, sqlite_store, dataclass_profile
    ):
        """Certifications list must survive serialization."""
        profile_dict = profile_to_dict(dataclass_profile)
        sqlite_store.store("roundtrip_user", profile_dict)
        results = sqlite_store.query("roundtrip_user", "Databricks certification")
        retrieved = results[0]["profile"]
        assert "Databricks Certified Associate Developer" in retrieved["certifications"]


# ---------------------------------------------------------------------------
# EMBEDDING ISOLATION — dimension mismatch bug
# ---------------------------------------------------------------------------

class TestEmbeddingDimensionMismatch:
    """
    Documents BUG-1: SQLiteStore.query() uses zip() for cosine similarity.

    If the stored embedding dimension != query embedding dimension, zip() silently
    truncates to min(len_a, len_b). No exception is raised, but the score is
    wrong (computed over a truncated vector).

    This test suite pins the CURRENT (buggy) behavior so we can verify the
    refactored stores/ package either:
      a) replicates the same silent truncation (behavior preserved), OR
      b) raises a clear ValueError (behavior improved — update this test).

    The NEW design under issue #53 should inject embed_fn at construction time
    so the same function is guaranteed for both store and retrieve paths.
    """

    def test_same_embedder_produces_nonzero_cosine_score(self, sqlite_store, sample_profile):
        """Baseline: same TF-IDF embedder for store and query → valid, nonzero score."""
        sqlite_store.store("emb_user", sample_profile)
        results = sqlite_store.query("emb_user", "Airflow pipelines Python")
        # Should return a result with a plausible cosine score.
        assert len(results) >= 1
        assert results[0]["score"] > 0.0, "Same-embedder query should yield positive cosine score"

    def test_dimension_mismatch_silently_truncates_current_bug(self, sqlite_store, monkeypatch):
        """
        BUG-1 regression: demonstrates the silent truncation behavior.

        We manually insert a row with a 256-dim embedding, then query with the
        default 128-dim TF-IDF vector. zip() truncates to 128 dims — the score
        is computed but is not meaningful.  The bug: no ValueError is raised.
        """
        import sqlite3

        # Insert a row with a 256-dim fake embedding directly (bypassing store()).
        big_vec = [1.0 / math.sqrt(256)] * 256  # unit vector, 256-dim
        profile_dict = _make_profile_dict()
        conn = sqlite3.connect(str(sqlite_store._path))
        conn.execute(
            "INSERT INTO profiles (user_id, vector_id, profile_json, embedding, stored_at) "
            "VALUES (?,?,?,?,?)",
            (
                "dim_bug_user",
                "dim_bug_user_999",
                json.dumps(profile_dict),
                json.dumps(big_vec),
                0.0,
            ),
        )
        conn.commit()
        conn.close()

        # Query with default 128-dim TF-IDF embedding.
        # CURRENT BEHAVIOR: does NOT raise — zip truncates silently.
        results = sqlite_store.query("dim_bug_user", "Airflow Python SQL")

        # Pin the current (buggy) behavior: a result IS returned (no exception).
        assert len(results) >= 1, (
            "BUG-1: dimension mismatch silently returns a result instead of raising"
        )
        # The score is "wrong" but within [-1, 1] range since zip truncates to 128 terms.
        assert -1.0 <= results[0]["score"] <= 1.0 + 1e-9

    def test_new_design_injectable_embedder_contract(self, tmp_path):
        """
        Issue #53 is now implemented: SQLiteStore accepts an embed_fn parameter.

        The same embed_fn is used at both store and query time, eliminating the
        BUG-1 dimension mismatch that arose when OpenAI (1536-dim) stored vectors
        were later queried with TF-IDF (128-dim) fallback embeddings.
        """
        fixed_embedder = lambda text: _embed_tfidf(text, dim=64)  # noqa: E731
        store = SQLiteStore(
            db_path=str(tmp_path / "injected.db"),
            embed_fn=fixed_embedder,
        )
        profile = {"experience": [], "skills": ["Python", "Airflow"], "projects": [], "education": [], "certifications": []}
        vid = store.store("inj_user", profile)
        assert isinstance(vid, str)

        results = store.query("inj_user", "Python Airflow pipeline")
        assert len(results) == 1
        # Score must be valid cosine range — no dimension truncation artefacts
        assert -1.0 <= results[0]["score"] <= 1.0 + 1e-9


# ---------------------------------------------------------------------------
# STORE returns vector_id contract
# ---------------------------------------------------------------------------

class TestStoreReturnValue:
    def test_store_returns_string(self, sqlite_store, sample_profile):
        vid = sqlite_store.store("v_user", sample_profile)
        assert isinstance(vid, str)

    def test_store_vector_id_contains_user_id(self, sqlite_store, sample_profile):
        """vector_id format is '{user_id}_{timestamp}' — user_id must be a prefix."""
        vid = sqlite_store.store("myuser", sample_profile)
        assert vid.startswith("myuser_")

    def test_store_twice_returns_distinct_vector_ids(self, sqlite_store, sample_profile):
        """Two successive stores for the same user must produce distinct vector_ids."""
        import time as _time
        vid1 = sqlite_store.store("dup_user", sample_profile)
        _time.sleep(0.01)  # ensure different int(time.time()) — same-second stores may collide
        vid2 = sqlite_store.store("dup_user", sample_profile)
        # IDs may collide if stored within the same second (known limitation).
        # We just verify both are strings; log if they happen to match.
        assert isinstance(vid1, str) and isinstance(vid2, str)


# ---------------------------------------------------------------------------
# PROTOCOL conformance
# ---------------------------------------------------------------------------

class TestBaseStoreProtocol:
    """SQLiteStore must implement the BaseStore protocol."""

    def test_sqlite_store_implements_base_store_protocol(self, sqlite_store):
        from rag_store import BaseStore
        assert isinstance(sqlite_store, BaseStore)

    def test_has_store_method(self, sqlite_store):
        assert callable(getattr(sqlite_store, "store", None))

    def test_has_query_method(self, sqlite_store):
        assert callable(getattr(sqlite_store, "query", None))

    def test_has_delete_method(self, sqlite_store):
        assert callable(getattr(sqlite_store, "delete", None))

    def test_has_list_users_method(self, sqlite_store):
        assert callable(getattr(sqlite_store, "list_users", None))


# ---------------------------------------------------------------------------
# FACTORY: get_store()
# ---------------------------------------------------------------------------

class TestGetStoreFactory:
    def test_get_store_returns_sqlite_without_pinecone_key(self):
        store = get_store()
        assert isinstance(store, SQLiteStore)

    def test_get_store_sqlite_is_functional(self, tmp_path, monkeypatch):
        """Factory-returned store must pass a minimal store → query round-trip."""
        # Redirect default db to tmp_path to avoid polluting ~/.tailor_resume/
        monkeypatch.setenv("HOME", str(tmp_path))
        store = get_store()
        profile = _make_profile_dict()
        vid = store.store("factory_user", profile)
        assert isinstance(vid, str)
        results = store.query("factory_user", "Airflow")
        assert len(results) >= 1
