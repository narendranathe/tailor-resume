"""Tests for ats_scorer.py -- Option B (formula), Option A (embedding), Option C (claude)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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


def test_claude_method_falls_back_to_formula_when_no_key():
    """Without anthropic or API key, claude method falls back to formula silently."""
    from ats_scorer import score
    # Simulate anthropic import failure (no package or no key)
    with patch.dict("sys.modules", {"anthropic": None}):
        result = score(JD, RESUME, method="claude")
    assert isinstance(result, ATSScoreResult)
    assert 0 <= result.score <= 100
    assert "fallback" in result.method_used


def _make_anthropic_mock(score_val: int = 78) -> MagicMock:
    """Build a minimal anthropic mock that returns a valid JSON score response."""
    payload = json.dumps({
        "score": score_val,
        "reasoning": "Strong Spark and Kafka alignment with JD.",
        "bullet_scores": [{"bullet": "Reduced ETL 73%", "score": 3}],
        "recommendations": ["Add Delta Lake examples", "Mention CI/CD tooling"],
    })
    content_block = SimpleNamespace(text=payload)
    response = SimpleNamespace(content=[content_block])
    mock_client = MagicMock()
    mock_client.messages.create.return_value = response
    mock_anthropic = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client
    return mock_anthropic


def test_claude_method_happy_path():
    from ats_scorer import score
    mock_anthropic = _make_anthropic_mock(score_val=78)
    with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
        result = score(JD, RESUME, method="claude")
    assert result.method_used == "claude"
    assert result.score == 78
    assert "Spark" in result.reasoning
    assert len(result.bullet_scores) == 1
    assert result.formula_score is not None


def test_claude_method_clamps_score():
    from ats_scorer import score
    mock_anthropic = _make_anthropic_mock(score_val=150)  # out of range
    with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
        result = score(JD, RESUME, method="claude")
    assert result.score == 100


def test_compare_returns_two_results():
    from ats_scorer import compare
    mock_anthropic = _make_anthropic_mock(score_val=82)
    with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
        formula_r, claude_r = compare(JD, RESUME)
    assert formula_r.method_used == "formula"
    assert claude_r.method_used == "claude"
    assert 0 <= formula_r.score <= 100
    assert 0 <= claude_r.score <= 100


def test_method_case_insensitive():
    from ats_scorer import score
    result = score(JD, RESUME, method="FORMULA")
    assert result.method_used == "formula"
