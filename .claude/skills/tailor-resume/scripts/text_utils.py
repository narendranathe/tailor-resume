"""
text_utils.py
Shared text extraction and analysis utilities for the tailor-resume pipeline.

Import rule: may only import from resume_types (no other sibling imports).

Usage:
    from text_utils import extract_metrics, extract_tools, tokenize, profile_dict_to_text
"""
from __future__ import annotations

import re
from typing import Dict, List

from resume_types import TOOL_VOCAB


# ---------------------------------------------------------------------------
# Metric extraction
# ---------------------------------------------------------------------------
# Issue #112: previously the patterns used capture groups and a `.{3,40}` tail
# for ranges, which (a) broke `re.findall` (it returned only the captured
# groups, not the full match) and (b) let "from 3 months to 14 days by owning
# CI/CD…" swallow 60+ chars of sentence trailer.
#
# New approach: use NON-capturing groups so `re.findall` yields the full match,
# bound each pattern to a concise numeric phrase, and cap every result at
# 30 chars as a safety net. The "from X to Y" range is built from explicit
# number-unit atoms so it cannot cross conjunctions, sentence boundaries, or
# additional digit tokens.
_TIME_UNIT = r"(?:ms|s|sec|secs|min|mins|hour|hours|hr|hrs|day|days|week|weeks|month|months|year|years)"
_VOLUME_UNIT = r"(?:rows?|users?|events?|requests?|tps|rps|qps|metrics?|records?|transactions?)"
# A single concise "number-with-unit" atom — number, optional +, optional unit
# word. Anchored on a digit boundary; the unit (if any) must be one short word.
_NUM_UNIT_ATOM = rf"\d+(?:\.\d+)?\+?\s?(?:%|{_TIME_UNIT}|{_VOLUME_UNIT})"

METRIC_PATTERNS = [
    # Range: "<num unit> to <num unit>" — both sides bounded, no greedy gap.
    rf"\b{_NUM_UNIT_ATOM}\s+to\s+{_NUM_UNIT_ATOM}\b",
    # Percentages (e.g. 45%, 95%+, 12.5%)
    r"\b\d+(?:\.\d+)?\s?%\+?",
    # Dollar amounts (e.g. $4,100, $1.2M, $50k)
    r"\$\s?\d[\d,]*(?:\.\d+)?[kmb]?",
    # Volume metrics (e.g. 100+ TPS, 5M users, 200 metrics)
    rf"\b\d+(?:\.\d+)?[kmb]?\+?\s?{_VOLUME_UNIT}\b",
    # Time durations (e.g. 3 months, 14 days, 45 min, 200 ms)
    rf"\b\d+(?:\.\d+)?\s?{_TIME_UNIT}\b",
    # Multipliers (e.g. 10x)
    r"\b\d+(?:\.\d+)?x\b",
]

# Defensive cap — see issue #112. Any single metric longer than this is a sign
# the regex over-matched and we drop it instead of returning a sentence trailer.
_METRIC_MAX_LEN = 30


def extract_metrics(text: str) -> List[str]:
    found: List[str] = []
    for pattern in METRIC_PATTERNS:
        for m in re.findall(pattern, text, flags=re.IGNORECASE):
            # `re.findall` returns strings when no group is captured and tuples
            # when groups are captured — all our groups are non-capturing, so
            # `m` is always a str. Keep the isinstance guard for safety.
            value = "".join(m) if isinstance(m, tuple) else m
            value = value.strip()
            if not value or len(value) > _METRIC_MAX_LEN:
                continue
            found.append(value)
    return list(dict.fromkeys(found))  # dedupe, preserve order


def extract_tools(text: str) -> List[str]:
    lower = text.lower()
    return [t for t in TOOL_VOCAB if t.lower() in lower]


def score_confidence(text: str) -> str:
    metrics = extract_metrics(text)
    if len(metrics) >= 2:
        return "high"
    if len(metrics) == 1:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Tokenizer (shared by jd_gap_analyzer and any future analysis)
# ---------------------------------------------------------------------------
STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "your",
    "you", "our", "are", "have", "has", "was", "were", "will", "can", "not",
    "using", "use", "job", "role", "work", "team", "strong", "experience",
    "ability", "skill", "skills", "knowledge", "understanding", "preferred",
    "required", "plus", "bonus", "nice", "good", "excellent", "great",
    "must", "minimum", "years", "year", "related", "relevant", "various",
    "including", "such", "etc", "well", "also", "both", "other", "new",
    "all", "any", "its", "may", "what", "how", "who", "able", "help",
}


def tokenize(text: str) -> List[str]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9\-/+.#]*", text.lower())
    return [t for t in tokens if t not in STOPWORDS and len(t) > 2]


def extract_phrases(text: str, n: int = 2) -> List[str]:
    """Extract n-grams for multi-word signal detection."""
    words = text.lower().split()
    return [" ".join(words[i:i+n]) for i in range(len(words) - n + 1)]


# ---------------------------------------------------------------------------
# Profile dict serialization (moved from rag_store._profile_to_text)
# ---------------------------------------------------------------------------
def profile_dict_to_text(profile: Dict) -> str:
    """Flatten a profile dict to searchable text for embedding."""
    parts: List[str] = []
    for role in profile.get("experience", []):
        parts.append(f"{role.get('title', '')} at {role.get('company', '')}")
        for b in role.get("bullets", []):
            parts.append(b.get("text", ""))
    for proj in profile.get("projects", []):
        parts.append(proj.get("name", ""))
        for b in proj.get("bullets", []):
            parts.append(b.get("text", ""))
    parts.extend(profile.get("skills", []))
    parts.extend(profile.get("certifications", []))
    return " ".join(parts)
