"""
ats_scorer.py
Unified ATS scoring facade with three engines:

  method="formula"   (Option B) -- 4-component formula, zero API keys needed
  method="embedding" (Option A) -- cosine similarity via text-embedding-3-small;
                                   falls back to TF-IDF if OPENAI_API_KEY not set
  method="claude"    (Option C) -- Claude-as-judge; lazily imports anthropic;
                                   falls back to formula if ANTHROPIC_API_KEY not set

Usage:
    from ats_scorer import score, compare
    result = score(jd_text, resume_text, method="formula")
    formula_r, claude_r = compare(jd_text, resume_text)  # side-by-side
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
        return _score_claude(jd, resume)

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


def _score_claude(jd: str, resume: str) -> ATSScoreResult:
    """
    Option C: Claude-as-judge scoring.
    Asks claude-haiku-4-5 to return a JSON evaluation of resume-vs-JD fit.
    Falls back to formula silently if anthropic is not installed or API key absent.
    """
    import json as _json
    import re as _re

    try:
        import anthropic  # lazy — keeps module importable without the dep

        prompt = (
            "You are an ATS (Applicant Tracking System) expert. "
            "Evaluate how well this resume matches the job description.\n\n"
            f"JOB DESCRIPTION:\n{jd[:1200]}\n\n"
            f"RESUME:\n{resume[:1200]}\n\n"
            "Return ONLY valid JSON — no prose, no fences — with exactly these keys:\n"
            '{"score": <int 0-100>, '
            '"reasoning": "<one sentence explaining the score>", '
            '"bullet_scores": [{"bullet": "<text>", "score": <0-3>}], '
            '"recommendations": ["<action phrase>"]}'
        )

        client = anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        # Strip accidental markdown fences
        raw = _re.sub(r"^```[a-z]*\n?", "", raw, flags=_re.MULTILINE)
        raw = _re.sub(r"\n?```$", "", raw, flags=_re.MULTILINE)
        parsed = _json.loads(raw.strip())

        score_val = max(0, min(100, int(parsed.get("score", 0))))
        formula_report = run_analysis(jd, resume, top_n=5)

        return ATSScoreResult(
            score=score_val,
            reasoning=str(parsed.get("reasoning", "")),
            bullet_scores=parsed.get("bullet_scores", []),
            recommendations=parsed.get("recommendations", formula_report.recommendations),
            method_used="claude",
            formula_score=formula_report.ats_score_estimate,
        )

    except Exception:
        # No API key, quota exceeded, parse failure — fall back silently
        fallback = _score_formula(jd, resume)
        return ATSScoreResult(
            score=fallback.score,
            reasoning=fallback.reasoning,
            bullet_scores=[],
            recommendations=fallback.recommendations,
            method_used="claude (formula fallback)",
            formula_score=fallback.score,
        )


def compare(jd: str, resume: str) -> Tuple[ATSScoreResult, ATSScoreResult]:
    """
    Returns (formula_result, claude_result) for side-by-side comparison UI.
    claude_result falls back to formula when ANTHROPIC_API_KEY is absent.
    """
    formula_result = score(jd, resume, method="formula")
    claude_result = score(jd, resume, method="claude")
    return formula_result, claude_result
