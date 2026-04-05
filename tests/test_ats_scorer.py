"""Tests for ats_scorer.py -- Option B (formula) and Option A (embedding)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "skills" / "tailor-resume" / "scripts"))

from resume_types import ATSScoreResult  # noqa: E402

JD = "Senior Data Engineer. Spark, Kafka, Airflow, Delta Lake, CI/CD, schema drift, data contracts."
RESUME = "Built Spark pipelines, Kafka consumers, Airflow DAGs. Reduced ETL 73% via CDC upserts."


def test_formula_method_returns_ats_score_result():
    from ats_scorer import score
    result = score(JD, RESUME, method="formula")
    assert isinstance(result, ATSScoreResult)
    assert 0 <= result.score <= 100


def test_formula_method_has_recommendations():
    from ats_scorer import score
    result = score(JD, RESUME, method="formula")
    assert isinstance(result.recommendations, list)
    assert len(result.recommendations) > 0


def test_formula_method_used_field():
    from ats_scorer import score
    result = score(JD, RESUME, method="formula")
    assert result.method_used == "formula"


def test_formula_score_none_for_formula_method():
    from ats_scorer import score
    result = score(JD, RESUME, method="formula")
    assert result.formula_score is None


def test_formula_bullet_scores_empty():
    from ats_scorer import score
    result = score(JD, RESUME, method="formula")
    assert result.bullet_scores == []


def test_embedding_method_with_mocked_embed():
    from ats_scorer import score
    # 256-dim vector (> 200) registers as "embedding" not tfidf
    fake_vec = [0.5] * 256
    with patch("rag_store.embed", return_value=fake_vec):
        result = score(JD, RESUME, method="embedding")
    assert isinstance(result, ATSScoreResult)
    assert 0 <= result.score <= 100
    assert "embedding" in result.method_used


def test_embedding_tfidf_fallback_label():
    from ats_scorer import score
    # 128-dim vector matches TF-IDF fallback size
    fake_vec = [0.5] * 128
    with patch("rag_store.embed", return_value=fake_vec):
        result = score(JD, RESUME, method="embedding")
    assert "tfidf fallback" in result.method_used


def test_embedding_formula_score_is_set():
    from ats_scorer import score
    fake_vec = [0.5] * 256
    with patch("rag_store.embed", return_value=fake_vec):
        result = score(JD, RESUME, method="embedding")
    assert result.formula_score is not None
    assert isinstance(result.formula_score, int)
    assert 0 <= result.formula_score <= 100


def test_embedding_score_in_range():
    from ats_scorer import score
    fake_vec = [0.3] * 256
    with patch("rag_store.embed", return_value=fake_vec):
        result = score(JD, RESUME, method="embedding")
    assert 0 <= result.score <= 100


def test_unknown_method_raises_value_error():
    from ats_scorer import score
    with pytest.raises(ValueError, match="Unknown method"):
        score(JD, RESUME, method="invalid_engine")


def test_claude_method_raises_not_implemented():
    from ats_scorer import score
    with pytest.raises(NotImplementedError, match="Issue #63"):
        score(JD, RESUME, method="claude")


def test_method_case_insensitive():
    from ats_scorer import score
    result = score(JD, RESUME, method="FORMULA")
    assert result.method_used == "formula"
