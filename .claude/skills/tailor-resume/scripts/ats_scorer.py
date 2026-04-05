"""
ats_scorer.py
Unified ATS scoring facade with three engines:

  method="formula"   (Option B) -- 4-component formula, zero API keys needed
  method="embedding" (Option A) -- cosine similarity via text-embedding-3-small;
                                   falls back to TF-IDF if OPENAI_API_KEY not set
  method="claude"    (Option C) -- Claude-as-judge; NOT YET IMPLEMENTED (see Issue #63)

Usage:
    from ats_scorer import score, compare
    result = score(jd_text, resume_text, method="formula")
    # compare() raises NotImplementedError for claude until Issue #63
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Tuple

_SCRIPTS = Path(__file__).parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from jd_gap_analyzer import run_analysis  # noqa: E402
from resume_types import ATSScoreResult  # noqa: E402


def _cosine(a: list, b: list) -> float:
    """Cosine similarity between two float vectors. Returns 0.0 for zero vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


def score(jd: str, resume: str, method: str = "formula") -> ATSScoreResult:
    """
    Score resume alignment against a JD using the specified engine.

    Args:
        jd: Full job description text.
        resume: Resume text (raw or JSON string from profile_extractor).
        method: "formula" | "embedding" | "claude"

    Returns:
        ATSScoreResult with score (0-100), reasoning, recommendations, method_used.

    Raises:
        ValueError: for unknown method values.
        NotImplementedError: for method="claude" until Issue #63 is implemented.
    """
    method = method.lower().strip()

    if method == "formula":
        return _score_formula(jd, resume)

    if method == "embedding":
        return _score_embedding(jd, resume)

    if method == "claude":
        raise NotImplementedError(
            "Claude scoring not yet implemented. Use method='formula' or method='embedding'. "
            "See Issue #63."
        )

    raise ValueError(f"Unknown method '{method}'. Use: formula | embedding | claude")


def _score_formula(jd: str, resume: str) -> ATSScoreResult:
    """Option B: 4-component formula (40% keyword + 30% category + 20% bullet + 10% seniority)."""
    report = run_analysis(jd, resume, top_n=5)
    reasoning = (
        report.recommendations[0]
        if report.recommendations
        else "Formula-based scoring using keyword overlap and category coverage."
    )
    return ATSScoreResult(
        score=report.ats_score_estimate,
        reasoning=reasoning,
        bullet_scores=[],
        recommendations=report.recommendations,
        method_used="formula",
        formula_score=None,
    )


def _score_embedding(jd: str, resume: str) -> ATSScoreResult:
    """
    Option A: Cosine similarity between JD and resume embeddings.
    Uses OpenAI text-embedding-3-small if OPENAI_API_KEY is set,
    otherwise falls back to TF-IDF character n-gram hashing (dim=128).
    """
    # Lazy import — avoids side effects at module load; rag_store may print warnings
    from rag_store import embed  # noqa: E402

    jd_vec = embed(jd)
    resume_vec = embed(resume)
    similarity = _cosine(jd_vec, resume_vec)
    embedding_score = max(0, min(100, int(similarity * 100)))

    # OpenAI text-embedding-3-small returns 1536-dim; TF-IDF fallback returns 128-dim
    method_label = "embedding" if len(jd_vec) > 200 else "embedding (tfidf fallback)"

    # Always run formula too — embeddings don't produce gap signals or recommendations
    formula_report = run_analysis(jd, resume, top_n=5)

    return ATSScoreResult(
        score=embedding_score,
        reasoning=f"Semantic embedding cosine similarity: {similarity:.3f}",
        bullet_scores=[],
        recommendations=formula_report.recommendations,
        method_used=method_label,
        formula_score=formula_report.ats_score_estimate,
    )


def compare(jd: str, resume: str) -> Tuple[ATSScoreResult, ATSScoreResult]:
    """
    Returns (claude_result, formula_result) for side-by-side comparison UI.
    Raises NotImplementedError for claude_result until Issue #63 is implemented.
    """
    formula_result = score(jd, resume, method="formula")
    claude_result = score(jd, resume, method="claude")  # raises NotImplementedError until #63
    return claude_result, formula_result
