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
    # Fix 12: sub-ms / sub-second latency
    r"\bsub[-\s]?(?:ms|millisecond|second|sec)\b",
    # Fix 12: headcount signals (e.g. "12-person team", "200 engineers")
    r"\b\d+[-\s]?(?:person|member|engineer|developer|employee|analyst)s?\b",
    # Fix 12: NPS scores
    r"\bNPS\s*(?:score\s*)?\d+",
    # Fix 12: ranked / top-N signals
    r"\b(?:top|ranked|rank)\s+\d+(?:\s*%|\s+of\s+\d+)?\b",
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


# ---------------------------------------------------------------------------
# Tool extraction
# ---------------------------------------------------------------------------
# Issue #113: bare substring matching produced false positives — short acronyms
# like "RAG", "AWS", "GCP", "DAX", "SQL" hit inside larger words ("tracking",
# "aware", "logcap", "fedax", "mysqlite"). Fix: anchor every vocab entry with
# `\b...\b` so word boundaries reject in-word matches.
#
# Follow-up (post-critique): collapse the N-per-call regex searches into a
# single IGNORECASE alternation regex. Word boundaries alone are enough to
# prevent false positives ("aws" in "jaws" fails the boundary check regardless
# of case), so the previous case-sensitive-for-acronyms branch is no longer
# necessary. Net effect: ~10x speedup on the hot path AND lowercase variants
# of acronyms ("sql queries", "dbt models") now correctly match.
def _is_acronym(token: str) -> bool:
    """Treat all-uppercase or all-lowercase single-word vocab entries as acronyms.

    Retained for any callers that introspect tool-vocab classification — the
    extract_tools matcher itself no longer branches on this because word
    boundaries provide the same false-positive protection without the
    case-sensitivity surprise documented in the #113 follow-up review.
    """
    if any(c.isspace() for c in token):
        return False
    letters = [c for c in token if c.isalpha()]
    if not letters:
        return False
    return all(c.isupper() for c in letters) or all(c.islower() for c in letters)


def _compile_tool_alternation():
    """Build a single IGNORECASE alternation regex covering every vocab entry.

    Longer patterns come first so multi-word entries (e.g. 'GitHub Actions')
    win over single-word ones ('GitHub') when both are in vocab.
    """
    if not TOOL_VOCAB:
        return None, {}
    patterns = sorted([re.escape(t) for t in TOOL_VOCAB], key=len, reverse=True)
    alt = re.compile(r"\b(?:" + "|".join(patterns) + r")\b", re.IGNORECASE)
    canonical = {t.lower(): t for t in TOOL_VOCAB}
    return alt, canonical


_TOOL_ALT_RE, _TOOL_CANONICAL = _compile_tool_alternation()


def extract_tools(text: str) -> List[str]:
    """Find tool/tech keywords from TOOL_VOCAB in `text`.

    Returns canonical-cased names in vocab order, deduplicated. Substring
    matches inside larger words are rejected via `\\b` anchors regardless of
    case (e.g. "aws" in "jaws" or "sql" in "mysqlite" never match).
    """
    if _TOOL_ALT_RE is None:
        return []
    found_lower = {m.group(0).lower() for m in _TOOL_ALT_RE.finditer(text)}
    return [t for t in TOOL_VOCAB if t.lower() in found_lower]


# ---------------------------------------------------------------------------
# Paren-aware delimiter split (skills / tech lists)
# ---------------------------------------------------------------------------
# Issue #114 and follow-up: a naive `re.split(r"[,;]", ...)` fragments inputs
# like "Azure (AKS, DevOps, Data Factory)" into 4 bogus entries. Multiple
# parsers (plain_parser, latex_parser, profile_extractor) had the same bug
# scattered across 5 call sites — this helper consolidates the fix.
def split_top_level(s: str, delims: str = ",;") -> List[str]:
    """Split `s` on any character in `delims` that is NOT inside parentheses.

    Preserves grouped tokens like 'Azure (AKS, DevOps)' as single entries.
    Handles: empty input, unmatched closing parens (depth clamped at 0),
    unmatched opening parens (tail captured intact), nested parens.
    """
    parts: List[str] = []
    buf: List[str] = []
    depth = 0
    delim_set = set(delims)
    for ch in s:
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch in delim_set and depth == 0:
            piece = "".join(buf).strip()
            if piece:
                parts.append(piece)
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


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
    # 2-char non-technical stop words (kept after Fix 2 raised min len to >=2)
    "in", "of", "be", "is", "it", "or", "at", "by", "an", "on", "do",
    "as", "if", "to", "we", "he", "me", "so", "no", "up", "am",
}


def tokenize(text: str) -> List[str]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9\-/+.#]*", text.lower())
    return [t for t in tokens if t not in STOPWORDS and len(t) >= 2]  # Fix 2: >=2 catches ml, ai, go, tf


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
