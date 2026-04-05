"""
resume_types.py
Shared data structures for the tailor-resume pipeline.

Import rule: stdlib + dataclasses only — no sibling imports.
All four pipeline scripts import from here; this module imports from nothing local.

Usage:
    from resume_types import Profile, GapReport, profile_to_dict
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Tool vocabulary — single source of truth across all scripts
# ---------------------------------------------------------------------------
TOOL_VOCAB: List[str] = [
    "Python", "SQL", "Bash", "Java", "Scala",
    "Spark", "Kafka", "Airflow", "Dagster", "dbt",
    "Docker", "Kubernetes", "Terraform",
    "Azure", "AWS", "GCP", "Databricks", "Delta Lake", "Iceberg",
    "Microsoft Fabric", "Power BI", "DAX",
    "FastAPI", "Flask", "React", "Streamlit",
    "PostgreSQL", "MySQL", "Redis", "Elasticsearch",
    "Pytest", "GitHub Actions", "Azure DevOps", "CI/CD",
    "MLflow", "LangChain", "RAG", "Pinecone", "pgvector",
    "Prometheus", "Grafana", "Monte Carlo", "Great Expectations",
]


# ---------------------------------------------------------------------------
# Profile types (owned by profile_extractor, consumed by all scripts)
# ---------------------------------------------------------------------------
@dataclass
class Bullet:
    text: str
    metrics: List[str]
    tools: List[str]
    evidence_source: str = "unknown"
    confidence: str = "medium"  # high | medium | low


@dataclass
class Role:
    title: str
    company: str
    start: str
    end: str
    location: str
    bullets: List[Bullet] = field(default_factory=list)


@dataclass
class Project:
    name: str
    tech: List[str]
    bullets: List[Bullet] = field(default_factory=list)
    date: str = ""


@dataclass
class Profile:
    experience: List[Role] = field(default_factory=list)
    projects: List[Project] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    education: List[Dict] = field(default_factory=list)
    certifications: List[str] = field(default_factory=list)


def profile_to_dict(profile: Profile) -> dict:
    return asdict(profile)


# ---------------------------------------------------------------------------
# Gap analysis types (owned by jd_gap_analyzer, consumed by cli.py)
# ---------------------------------------------------------------------------
@dataclass
class GapSignal:
    category: str
    jd_keywords: List[str]
    jd_frequency: int
    resume_coverage: float        # 0.0 – 1.0
    priority: str                 # high | medium | low
    suggested_angles: List[str]


@dataclass
class GapReport:
    top_missing: List[GapSignal]
    keyword_gaps: List[Tuple[str, int]]   # (keyword, jd_freq) missing from resume
    ats_score_estimate: int               # 0-100 rough estimate
    recommendations: List[str]
    user_id: str = ""                     # opaque tenant key; empty = anonymous
