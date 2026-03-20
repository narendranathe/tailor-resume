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
METRIC_PATTERNS = [
    r"\b\d+(\.\d+)?\s?%",                        # percentages
    r"\$\s?\d[\d,]*(\.\d+)?[kmb]?",               # dollar amounts
    r"\b\d+[kmb]?\+?\s?(rows|users|events|tps|rps|requests)",  # volume
    r"\b\d+\s?(ms|s|sec|min|hours|days|weeks)\b", # time
    r"\bfrom\b.{3,40}\bto\b.{3,40}",              # from X to Y
    r"\b\d+x\b",                                   # multipliers
]


def extract_metrics(text: str) -> List[str]:
    found: List[str] = []
    for pattern in METRIC_PATTERNS:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        for m in matches:
            found.append("".join(m) if isinstance(m, tuple) else m)
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
