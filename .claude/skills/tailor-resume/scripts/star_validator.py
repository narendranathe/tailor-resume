"""
star_validator.py
STAR method enforcement for resume bullets.

Every bullet must have:
  - Action: a strong action verb (what you DID)
  - Result: a measurable outcome (%, $, time, count)
  - Word count <= MAX_BULLET_WORDS (hard 2-line limit)

Situation and Task are embedded in the role header above the bullet,
not stated explicitly in the bullet text (resume compression standard).

Import rule: stdlib + resume_types only — no other sibling imports.

Usage:
    from star_validator import score_star, bullet_quality_score, STARScore
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List


MAX_BULLET_WORDS = 20  # hard 2-line limit at 11pt in standard resume layout

# Strong action verbs that open or anchor a resume bullet
ACTION_VERBS: set = {
    "accelerated", "achieved", "architected", "automated", "built",
    "centralized", "consolidated", "containerized", "cut", "decreased",
    "delivered", "deployed", "designed", "developed", "drove",
    "eliminated", "enabled", "engineered", "established", "expanded",
    "generated", "governed", "grew", "implemented", "improved",
    "increased", "integrated", "launched", "led", "maintained",
    "migrated", "modernized", "optimized", "orchestrated", "owned",
    "partitioned", "pioneered", "prevented", "productionized", "raised",
    "redesigned", "reduced", "refactored", "replaced", "restructured",
    "scaled", "shipped", "standardized", "streamlined", "transformed",
    "unified", "upgraded",
}

# Outcome/result signal words (complement to numeric patterns)
RESULT_SIGNAL_WORDS: set = {
    "saving", "saved", "reduced", "reducing", "cut", "cutting",
    "improved", "improving", "prevented", "preventing", "eliminated",
    "eliminating", "accelerated", "achieving", "delivering", "enabling",
    "generating", "increasing", "decreasing",
}

# Metric patterns (subset of text_utils.METRIC_PATTERNS, kept here to avoid circular import)
_METRIC_PATTERNS: List[str] = [
    r"\b\d+(\.\d+)?\s?%",                          # percentages: 73%, 40.5%
    r"\$\s?\d[\d,]*(\.\d+)?[kmb]?",                # dollars: $3k, $1.2M
    r"\b\d+[kmb]?\+?\s?(rows|users|events|tps|rps|requests|pipelines|clients)",  # volume
    r"\b\d+\s?(ms|s|sec|min|hours|days|weeks)\b",  # time
    r"\bfrom\b.{3,40}\bto\b.{3,40}",               # from X to Y pattern
    r"\b\d+x\b",                                    # multipliers: 3x, 10x
    r"\b\d{2,}\b",                                  # bare numbers >= 10 (scale signals)
]


def _has_action(text: str) -> bool:
    """Check whether the bullet contains a strong action verb."""
    first_words = text.lower().split()[:6]  # check opening words
    all_words = set(text.lower().split())
    # Strong if an action verb appears in first 6 words OR anywhere in short bullets
    return bool(ACTION_VERBS & (set(first_words) | (all_words if len(all_words) <= 12 else set())))


def _has_result(text: str) -> bool:
    """Check whether the bullet contains a measurable result."""
    for pattern in _METRIC_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True
    # Check outcome signal words followed by a comparative context
    lower = text.lower()
    for word in RESULT_SIGNAL_WORDS:
        if word in lower:
            return True
    return False


@dataclass
class STARScore:
    has_action: bool
    has_result: bool
    word_count: int
    star_score: int          # 0-2: one point per component (Action + Result)
    passes: bool             # True iff star_score == 2 AND word_count <= MAX_BULLET_WORDS
    violations: List[str] = field(default_factory=list)


def score_star(text: str) -> STARScore:
    """
    Score a single bullet for STAR compliance and word count.

    Returns STARScore with:
      - has_action: strong action verb detected
      - has_result: metric or outcome signal detected
      - word_count: number of words in text
      - star_score: 0-2 (1 per component)
      - passes: star_score == 2 AND word_count <= MAX_BULLET_WORDS
      - violations: human-readable list of what's missing
    """
    text = text.strip()
    words = text.split()
    word_count = len(words)

    has_action = _has_action(text)
    has_result = _has_result(text)
    star_score = int(has_action) + int(has_result)
    passes = star_score == 2 and word_count <= MAX_BULLET_WORDS

    violations: List[str] = []
    if not has_action:
        violations.append("missing action verb (use: built, reduced, migrated, automated...)")
    if not has_result:
        violations.append("missing measurable result (add %, $, time, count, or before/after)")
    if word_count > MAX_BULLET_WORDS:
        violations.append(f"too long: {word_count} words (limit {MAX_BULLET_WORDS})")

    return STARScore(
        has_action=has_action,
        has_result=has_result,
        word_count=word_count,
        star_score=star_score,
        passes=passes,
        violations=violations,
    )


def bullet_quality_score(bullet: Dict) -> float:
    """
    Composite bullet quality score: 0.0 to 1.0.

    Weights:
      0.50 — STAR compliance (action + result, each 0.25)
      0.30 — metric density (from bullet['metrics'] list)
      0.10 — tool specificity (from bullet['tools'] list)
      0.10 — confidence signal (from bullet['confidence'] field)

    Input: a bullet dict with keys text, metrics, tools, confidence.
    """
    text = bullet.get("text", "")
    metrics = bullet.get("metrics", [])
    tools = bullet.get("tools", [])
    confidence = bullet.get("confidence", "low")

    s = score_star(text)

    # STAR component scores (0.25 each)
    star_part = (0.25 if s.has_action else 0.0) + (0.25 if s.has_result else 0.0)

    # Metric density: 0 metrics=0, 1=0.15, 2+=0.30
    metric_part = min(len(metrics) * 0.15, 0.30)

    # Tool specificity: 0 tools=0, 1+=0.10
    tool_part = 0.10 if tools else 0.0

    # Confidence: high=0.10, medium=0.05, low=0.0
    confidence_map = {"high": 0.10, "medium": 0.05, "low": 0.0}
    conf_part = confidence_map.get(confidence, 0.0)

    return round(min(star_part + metric_part + tool_part + conf_part, 1.0), 3)


def enforce_star(bullets: List[Dict]) -> List[Dict]:
    """
    Add star_score, star_passes, and star_violations fields to each bullet dict.
    Non-destructive — original keys are preserved.
    """
    result = []
    for b in bullets:
        s = score_star(b.get("text", ""))
        result.append({
            **b,
            "star_score": s.star_score,
            "star_passes": s.passes,
            "star_violations": s.violations,
        })
    return result
