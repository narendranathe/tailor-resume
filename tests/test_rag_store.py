"""Tests for rag_store.py — SQLite backend, embeddings, factory (no API keys required)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude/skills/tailor-resume/scripts"))

from rag_store import (
    _profile_to_text,
    _embed_tfidf,
    embed,
    SQLiteStore,
    get_store,
)

SAMPLE_PROFILE = {
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


# ---------------------------------------------------------------------------
# _profile_to_text
# ---------------------------------------------------------------------------
class TestProfileToText:
    def test_returns_string(self):
        text = _profile_to_text(SAMPLE_PROFILE)
        assert isinstance(text, str)

    def test_includes_title(self):
        text = _profile_to_text(SAMPLE_PROFILE)
        assert "Senior Data Engineer" in text

    def test_includes_bullets(self):
        text = _profile_to_text(SAMPLE_PROFILE)
        assert "Databricks" in text or "CI/CD" in text

    def test_includes_skills(self):
        text = _profile_to_text(SAMPLE_PROFILE)
        assert "Python" in text

    def test_includes_certifications(self):
        text = _profile_to_text(SAMPLE_PROFILE)
        assert "AWS Certified Data Engineer" in text

    def test_includes_project_bullets(self):
        text = _profile_to_text(SAMPLE_PROFILE)
        assert "Spark" in text or "Analytics Pipeline" in text

    def test_empty_profile_returns_string(self):
        text = _profile_to_text({})
        assert isinstance(text, str)

    def test_profile_without_projects(self):
        profile = {"experience": [], "projects": [], "skills": ["Python"], "certifications": []}
        text = _profile_to_text(profile)
        assert "Python" in text


# ---------------------------------------------------------------------------
# _embed_tfidf
# ---------------------------------------------------------------------------
class TestEmbedTfidf:
    def test_returns_list_of_floats(self):
        vec = _embed_tfidf("airflow spark python data quality")
        assert isinstance(vec, list)
        assert all(isinstance(v, float) for v in vec)

    def test_vector_length_matches_dim(self):
        vec = _embed_tfidf("airflow spark", dim=64)
        assert len(vec) == 64

    def test_default_dim_is_128(self):
        vec = _embed_tfidf("airflow spark")
        assert len(vec) == 128

    def test_vector_is_normalized(self):
        import math
        vec = _embed_tfidf("airflow spark python")
        norm = math.sqrt(sum(v * v for v in vec))
        assert abs(norm - 1.0) < 1e-6

    def test_empty_string_returns_zero_vector(self):
        vec = _embed_tfidf("")
        assert len(vec) == 128
        # Norm is 0 → normalized to all zeros (norm=1 by fallback)
        assert all(v == 0.0 for v in vec)

    def test_different_texts_produce_different_vectors(self):
        v1 = _embed_tfidf("airflow orchestration")
        v2 = _embed_tfidf("machine learning tensorflow")
        assert v1 != v2


# ---------------------------------------------------------------------------
# embed — fallback path (no OPENAI_API_KEY)
# ---------------------------------------------------------------------------
class TestEmbedFallback:
    def test_embed_uses_tfidf_without_api_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        vec = embed("airflow spark python")
        assert isinstance(vec, list)
        assert len(vec) == 128

    def test_embed_returns_floats(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        vec = embed("data quality pipeline")
        assert all(isinstance(v, float) for v in vec)


# ---------------------------------------------------------------------------
# SQLiteStore
# ---------------------------------------------------------------------------
class TestSQLiteStore:
    @pytest.fixture
    def store(self, tmp_path):
        db_path = tmp_path / "test_profiles.db"
        return SQLiteStore(db_path=str(db_path))

    def test_store_returns_vector_id(self, store, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        vid = store.store("user1", SAMPLE_PROFILE)
        assert isinstance(vid, str)
        assert "user1" in vid

    def test_store_and_query_returns_results(self, store, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        store.store("user1", SAMPLE_PROFILE)
        results = store.query("user1", "airflow data quality")
        assert isinstance(results, list)
        assert len(results) >= 1

    def test_query_result_has_score_and_profile(self, store, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        store.store("user1", SAMPLE_PROFILE)
        results = store.query("user1", "airflow")
        assert "score" in results[0]
        assert "profile" in results[0]

    def test_query_unknown_user_returns_empty(self, store, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        results = store.query("nonexistent_user", "airflow")
        assert results == []

    def test_list_users_returns_stored_user(self, store, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        store.store("alice", SAMPLE_PROFILE)
        users = store.list_users()
        assert "alice" in users

    def test_list_users_empty_store(self, store):
        users = store.list_users()
        assert users == []

    def test_delete_removes_user_profiles(self, store, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        store.store("bob", SAMPLE_PROFILE)
        store.delete("bob")
        users = store.list_users()
        assert "bob" not in users

    def test_delete_nonexistent_user_does_not_raise(self, store):
        store.delete("ghost_user")  # Should not raise

    def test_multiple_users_isolated(self, store, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        store.store("alice", SAMPLE_PROFILE)
        store.store("bob", SAMPLE_PROFILE)
        users = store.list_users()
        assert "alice" in users
        assert "bob" in users

    def test_top_k_limits_results(self, store, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        store.store("user1", SAMPLE_PROFILE)
        store.store("user1", SAMPLE_PROFILE)
        store.store("user1", SAMPLE_PROFILE)
        results = store.query("user1", "airflow", top_k=2)
        assert len(results) <= 2


# ---------------------------------------------------------------------------
# get_store factory
# ---------------------------------------------------------------------------
class TestGetStore:
    def test_returns_sqlite_when_no_pinecone_key(self, monkeypatch):
        monkeypatch.delenv("PINECONE_API_KEY", raising=False)
        store = get_store()
        assert isinstance(store, SQLiteStore)

    def test_sqlite_store_is_functional(self, monkeypatch, tmp_path):
        monkeypatch.delenv("PINECONE_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        # Override the default db path via env is not needed; just verify it works
        store = get_store()
        assert hasattr(store, "store")
        assert hasattr(store, "query")
        assert hasattr(store, "delete")
        assert hasattr(store, "list_users")
