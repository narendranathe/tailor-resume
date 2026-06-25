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
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Tool vocabulary — single source of truth across all scripts
# ---------------------------------------------------------------------------
TOOL_VOCAB: List[str] = [
    # Languages (Fix 7)
    "Python", "SQL", "Bash", "Java", "Scala", "TypeScript", "JavaScript",
    "Go", "Rust", "C++", "Node.js",
    # Stream & batch processing
    "Spark", "PySpark", "Flink", "Kafka", "Kinesis", "Pub/Sub",
    "Apache Beam", "Pulsar", "RabbitMQ",
    # Orchestration
    "Airflow", "Dagster", "Prefect", "Celery",
    # Transformation & modeling
    "dbt", "dbt Core", "dbt Cloud",
    # Ingestion & ELT
    "Fivetran", "Airbyte", "Stitch", "Glue",
    # Infra & containers
    "Docker", "Kubernetes", "Terraform", "Helm", "ArgoCD", "Ansible", "Pulumi",
    # Cloud platforms
    "Azure", "AWS", "GCP", "Databricks", "EMR", "Dataflow",
    # Table formats & storage
    "Delta Lake", "Iceberg", "Parquet", "HDFS", "Hive",
    # Cloud warehouses & query engines
    "Snowflake", "BigQuery", "Redshift", "Microsoft Fabric", "Trino", "Presto",
    # BI & visualization
    "Power BI", "DAX", "Looker", "Tableau", "Superset", "Metabase",
    # Web frameworks & APIs
    "FastAPI", "Flask", "React", "Streamlit", "gRPC", "GraphQL",
    # Databases
    "PostgreSQL", "MySQL", "Redis", "Elasticsearch", "Hadoop",
    # Testing & CI/CD
    "Pytest", "GitHub Actions", "Azure DevOps", "CI/CD", "Jenkins", "CircleCI",
    # ML & AI
    "MLflow", "LangChain", "LangGraph", "RAG", "Pinecone", "pgvector",
    "Pandas", "NumPy", "scikit-learn", "PyTorch", "TensorFlow",
    "HuggingFace", "LlamaIndex", "Milvus", "Weaviate", "ChromaDB", "OpenAI",
    # Observability & quality
    "Prometheus", "Grafana", "Monte Carlo", "Great Expectations", "Soda",
    "OpenTelemetry", "Jaeger", "Datadog", "Splunk",
    # Collaboration
    "JIRA", "Confluence", "Notion",
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
    summary: str = ""  # Enhancement #5: captured from Summary/Profile/Objective section
    contact: Dict = field(default_factory=dict)  # Enhancement #4: {name, email, phone, linkedin, github}


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


# ---------------------------------------------------------------------------
# ATS scoring result (owned by ats_scorer, consumed by api_server + mcp_server)
# ---------------------------------------------------------------------------
@dataclass
class ATSScoreResult:
    """Result from any ATS scoring engine (formula, embedding, or Claude)."""
    score: int                           # 0-100
    reasoning: str                       # human-readable explanation
    bullet_scores: List[Dict]            # per-bullet feedback (empty for non-Claude methods)
    recommendations: List[str]           # actionable improvement strings
    method_used: str                     # "formula" | "embedding" | "claude" | "formula (fallback)"
    formula_score: Optional[int] = None  # set when method_used != "formula"
