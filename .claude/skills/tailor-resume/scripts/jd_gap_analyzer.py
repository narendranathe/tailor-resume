"""
jd_gap_analyzer.py
Analyzes a job description against a candidate profile and returns
prioritized gaps with suggested angles for closing them.

Usage:
    python jd_gap_analyzer.py --jd jd.txt --profile profile.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from typing import Dict, List, Tuple

from resume_types import GapReport, GapSignal
from text_utils import tokenize


# ---------------------------------------------------------------------------
# Signal taxonomy — maps abstract signal categories to JD keywords
# ---------------------------------------------------------------------------
SIGNAL_TAXONOMY: Dict[str, List[str]] = {
    "testing_ci_cd": [
        "test", "testing", "pytest", "unit test", "integration test",
        "ci", "cd", "ci/cd", "github actions", "azure devops", "devops",
        "pipeline", "build", "deploy", "deployment", "automation",
    ],
    "data_quality_observability": [
        "data quality", "data contract", "schema", "schema enforcement",
        "observability", "monitoring", "anomaly", "great expectations",
        "monte carlo", "soda", "freshness", "null rate", "volume check",
    ],
    "orchestration": [
        "airflow", "dagster", "prefect", "databricks jobs", "orchestration",
        "dag", "workflow", "scheduling", "backfill", "retry", "idempotent",
    ],
    "semantic_layer_governance": [
        "semantic layer", "metrics layer", "governed metrics", "dbt",
        "business logic", "single source", "lineage", "catalog", "governance",
        "rbac", "access control",
    ],
    "architecture_finops": [
        "architecture", "cost", "finops", "tco", "cloud cost", "optimize",
        "partition", "pruning", "compaction", "delta lake", "iceberg",
        "open table", "parquet", "storage", "compute",
    ],
    "streaming_realtime": [
        "streaming", "real-time", "kafka", "kinesis", "pubsub", "flink",
        "spark streaming", "event", "events", "latency", "throughput",
    ],
    "ml_ai_platform": [
        "ml", "machine learning", "model", "mlflow", "feature store",
        "inference", "training", "llm", "rag", "embedding", "vector",
        "langchain", "openai", "ai platform",
    ],
    "cloud_infra": [
        "azure", "aws", "gcp", "cloud", "kubernetes", "k8s", "docker",
        "terraform", "iac", "infrastructure", "container", "microservices",
    ],
    "leadership_ownership": [
        "lead", "leading", "mentor", "mentoring", "ownership", "cross-functional",
        "stakeholder", "communication", "roadmap", "strategy", "decision",
    ],
    "sql_data_modeling": [
        "sql", "data model", "data modeling", "dimensional", "star schema",
        "snowflake schema", "normalization", "olap", "oltp", "dw", "data warehouse",
    ],
}


SUGGESTED_ANGLES: Dict[str, List[str]] = {
    "testing_ci_cd": [
        "Describe a test suite you built (language, scope, incident reduction).",
        "Show CI/CD pipeline ownership: deploy frequency, build time, validation steps.",
    ],
    "data_quality_observability": [
        "Quantify incidents prevented by quality checks (support tickets, bad loads, audits).",
        "Show schema enforcement or data contract implementation with business impact.",
    ],
    "orchestration": [
        "Show Airflow/Dagster ownership with SLA, backfill strategy, and retry policy.",
        "Quantify pipeline reliability improvement (uptime, failure rate, MTTR).",
    ],
    "semantic_layer_governance": [
        "Describe governed metric definitions and how many consumers rely on them.",
        "Show discrepancy reduction: metric disagreements dropped from X to 0.",
    ],
    "architecture_finops": [
        "Lead with a cost win: $X/month saved, X% compute reduction.",
        "Explain a trade-off decision (streaming vs batch, cost vs freshness).",
    ],
    "streaming_realtime": [
        "Show streaming system at scale: TPS, latency, and consumer count.",
        "Describe fault-tolerance design (DLQ, idempotency, consumer lag monitoring).",
    ],
    "ml_ai_platform": [
        "Show data platform contribution to ML: feature store, model serving reliability.",
        "Describe LLM-ready datasets or retrieval infrastructure you built.",
    ],
    "cloud_infra": [
        "Quantify infra optimization: cost reduction, autoscaling wins, node consolidation.",
        "Show IaC ownership and deployment reliability.",
    ],
    "leadership_ownership": [
        "Show cross-functional work: stakeholders, scope, decision authority.",
        "Describe mentoring or team capability building with concrete outcomes.",
    ],
    "sql_data_modeling": [
        "Show data model design decisions and the business problem they solved.",
        "Quantify query performance improvements from schema/index changes.",
    ],
}


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------
def analyze_category_coverage(
    jd_text: str, resume_text: str
) -> Dict[str, Dict]:
    """Score each signal category based on JD presence vs resume coverage."""
    jd_lower = jd_text.lower()
    resume_lower = resume_text.lower()
    results = {}

    for category, keywords in SIGNAL_TAXONOMY.items():
        jd_hits = [kw for kw in keywords if kw in jd_lower]
        resume_hits = [kw for kw in jd_hits if kw in resume_lower]
        jd_freq = sum(jd_lower.count(kw) for kw in jd_hits)
        coverage = len(resume_hits) / len(jd_hits) if jd_hits else 1.0

        results[category] = {
            "jd_keywords": jd_hits,
            "jd_frequency": jd_freq,
            "resume_coverage": round(coverage, 2),
            "missing_keywords": [kw for kw in jd_hits if kw not in resume_lower],
        }

    return results


def build_gap_signals(
    category_coverage: Dict[str, Dict], top_n: int = 5
) -> List[GapSignal]:
    signals = []
    for category, data in category_coverage.items():
        if not data["jd_keywords"]:
            continue
        coverage = data["resume_coverage"]
        freq = data["jd_frequency"]
        priority = (
            "high" if coverage < 0.3 and freq >= 2
            else "medium" if coverage < 0.6 and freq >= 1
            else "low"
        )
        if priority in ("high", "medium"):
            signals.append(GapSignal(
                category=category.replace("_", " ").title(),
                jd_keywords=data["jd_keywords"],
                jd_frequency=freq,
                resume_coverage=coverage,
                priority=priority,
                suggested_angles=SUGGESTED_ANGLES.get(category, []),
            ))

    signals.sort(key=lambda s: (0 if s.priority == "high" else 1, -s.jd_frequency))
    return signals[:top_n]


def keyword_gaps(
    jd_text: str, resume_text: str, min_freq: int = 2, top_n: int = 10
) -> List[Tuple[str, int]]:
    jd_counts = Counter(tokenize(jd_text))
    resume_tokens = set(tokenize(resume_text))
    gaps = [
        (term, freq)
        for term, freq in jd_counts.items()
        if freq >= min_freq and term not in resume_tokens and len(term) > 3
    ]
    gaps.sort(key=lambda x: x[1], reverse=True)
    return gaps[:top_n]


def estimate_ats_score(
    jd_text: str, resume_text: str, category_coverage: Dict[str, Dict]
) -> int:
    """Rough ATS score estimate (0-100)."""
    jd_tokens = set(tokenize(jd_text))
    resume_tokens = set(tokenize(resume_text))
    keyword_overlap = len(jd_tokens & resume_tokens) / max(len(jd_tokens), 1)

    category_scores = [
        v["resume_coverage"]
        for v in category_coverage.values()
        if v["jd_keywords"]
    ]
    avg_category = sum(category_scores) / max(len(category_scores), 1)

    score = int((0.5 * keyword_overlap + 0.5 * avg_category) * 100)
    return min(score, 100)


def run_analysis(
    jd_text: str,
    resume_text: str,
    top_n: int = 5,
) -> GapReport:
    category_coverage = analyze_category_coverage(jd_text, resume_text)
    top_missing = build_gap_signals(category_coverage, top_n=top_n)
    kw_gaps = keyword_gaps(jd_text, resume_text)
    ats_score = estimate_ats_score(jd_text, resume_text, category_coverage)

    recommendations = []
    if ats_score < 50:
        recommendations.append("Critical: fewer than half of JD keywords appear in resume — prioritize gap closure before any formatting work.")
    if any(s.category == "Testing Ci Cd" for s in top_missing):
        recommendations.append("Add at least 2 bullets demonstrating tests + CI/CD ownership with incident/defect reduction metrics.")
    if any(s.category == "Data Quality Observability" for s in top_missing):
        recommendations.append("Add data quality implementation bullet with measurable outcome (tickets reduced, incidents prevented).")
    if not recommendations:
        recommendations.append("Good keyword coverage — focus on strengthening metrics and compressing to one page.")

    return GapReport(
        top_missing=top_missing,
        keyword_gaps=kw_gaps,
        ats_score_estimate=ats_score,
        recommendations=recommendations,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze JD vs resume gaps.")
    parser.add_argument("--jd", required=True, help="Path to JD text file")
    parser.add_argument("--profile", required=True, help="Path to profile JSON or plain resume text")
    parser.add_argument("--top", type=int, default=5, help="Number of top gaps to report")
    args = parser.parse_args()

    with open(args.jd, encoding="utf-8") as f:
        jd_text = f.read()

    with open(args.profile, encoding="utf-8") as f:
        raw = f.read()

    # Accept either plain text or JSON profile
    try:
        profile_data = json.loads(raw)
        # Flatten JSON profile to text for analysis
        resume_text = json.dumps(profile_data)
    except json.JSONDecodeError:
        resume_text = raw

    report = run_analysis(jd_text, resume_text, top_n=args.top)

    print("\n=== ATS Score Estimate ===")
    print(f"  {report.ats_score_estimate}/100")

    print("\n=== Top Missing / Weak Signals ===")
    for i, gap in enumerate(report.top_missing, 1):
        print(f"\n{i}. [{gap.priority.upper()}] {gap.category}")
        print(f"   JD keywords: {', '.join(gap.jd_keywords[:5])}")
        print(f"   Resume coverage: {int(gap.resume_coverage * 100)}%")
        print("   Suggested angles:")
        for angle in gap.suggested_angles:
            print(f"     - {angle}")

    print("\n=== Keyword Gaps (missing from resume, frequent in JD) ===")
    for term, freq in report.keyword_gaps:
        print(f"  '{term}' (JD frequency: {freq})")

    print("\n=== Recommendations ===")
    for rec in report.recommendations:
        print(f"  \u2022 {rec}")


if __name__ == "__main__":
    main()
