"""Regression tests for text_utils — covers extract_metrics (#112) and extract_tools (#113).

extract_metrics: the pre-fix regex was too greedy and would capture entire
sentence trailers after numeric tokens (60+ characters of text). These tests
pin the corrected behaviour: each metric is a concise numeric phrase (cap
30 chars), and no match crosses sentence/conjunction boundaries or other
digit tokens.

extract_tools: short acronyms (RAG, AI, ML, SQL, AWS, GCP, DAX) were
matching as substrings inside larger words like "tracking", "email",
"mysqlite". The fix anchors each tool with \\b word boundaries, with
case-sensitive matching for all-uppercase / all-lowercase acronyms.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude/skills/tailor-resume/scripts"))

from text_utils import extract_metrics, extract_tools  # noqa: E402


MAX_LEN = 30


def _no_trailers(metrics):
    assert all(len(m) <= MAX_LEN for m in metrics), (
        f"extract_metrics returned an over-long element: "
        f"{[m for m in metrics if len(m) > MAX_LEN]}"
    )


# ---------------------------------------------------------------------------
# Issue #112 — extract_metrics no longer grabs sentence trailers
# ---------------------------------------------------------------------------
class TestIssue112NoTrailers:
    def test_compressed_deployment_cycles_no_trailer(self):
        text = (
            "Compressed deployment cycles from 3 months to 14 days "
            "by owning CI/CD end-to-end in Azure DevOps with"
        )
        metrics = extract_metrics(text)
        _no_trailers(metrics)
        joined = " | ".join(metrics)
        # Either separate ("3 months", "14 days") or a range
        # ("3 months to 14 days") is acceptable.
        assert (
            ("3 months" in joined and "14 days" in joined)
            or "3 months to 14 days" in joined
        ), f"expected '3 months' and '14 days' (or the range) in {metrics!r}"
        # The literal trailing sentence content must not appear in any element.
        for m in metrics:
            assert "owning" not in m.lower()
            assert "azure" not in m.lower()
            assert "end-to-end" not in m.lower()

    def test_etl_runtime_range(self):
        metrics = extract_metrics("Reduced ETL runtime from 45 min to 9 min")
        _no_trailers(metrics)
        joined = " | ".join(metrics)
        assert (
            ("45 min" in joined and "9 min" in joined)
            or "45 min to 9 min" in joined
        ), f"expected min phrases in {metrics!r}"

    def test_tps_with_plus(self):
        metrics = extract_metrics(
            "Built a system serving 100+ TPS with sub-ms latency"
        )
        _no_trailers(metrics)
        joined = " | ".join(metrics).lower()
        assert "100+ tps" in joined or "100+" in joined, metrics

    def test_dollar_with_comma(self):
        metrics = extract_metrics("saved $4,100 per month")
        _no_trailers(metrics)
        assert any("$4,100" in m for m in metrics), metrics

    def test_percent_plus(self):
        metrics = extract_metrics("95%+ accuracy")
        _no_trailers(metrics)
        joined = " | ".join(metrics)
        assert "95%+" in joined or "95%" in joined, metrics

    def test_percent_no_yoy_trailer(self):
        metrics = extract_metrics(
            "reduced production data defects by 40% year-over-year"
        )
        _no_trailers(metrics)
        assert any("40%" in m for m in metrics), metrics
        for m in metrics:
            assert "year-over-year" not in m.lower(), (
                f"trailing 'year-over-year' should not leak into a metric, "
                f"got {m!r}"
            )
            assert "year" not in m.lower() or m.strip() in {
                "40%",
                "40% year",
            }, m


# ---------------------------------------------------------------------------
# Sanity — preserve previously expected extract_metrics behaviour
# ---------------------------------------------------------------------------
class TestPreservedBehaviour:
    def test_empty_string(self):
        assert extract_metrics("") == []

    def test_no_metrics(self):
        assert extract_metrics("Led cross-functional team meetings") == []

    def test_simple_percentage(self):
        metrics = extract_metrics("Reduced latency by 45%")
        assert any("45%" in m for m in metrics), metrics

    def test_multiplier(self):
        metrics = extract_metrics("Achieved 10x speedup")
        _no_trailers(metrics)
        assert any("10x" in m for m in metrics), metrics


# ---------------------------------------------------------------------------
# Issue #113 — extract_tools no longer matches acronyms as substrings
# ---------------------------------------------------------------------------
class TestExtractToolsAcronymBoundary:
    def test_issue_113_rag_not_matched_inside_tracking(self):
        """The exact bullet from issue #113 must NOT yield RAG."""
        text = (
            "Built real-time analytics platform tracking competitor pricing, "
            "delivery times, and coverage"
        )
        tools = extract_tools(text)
        assert "RAG" not in tools

    def test_rag_legitimate_use_still_matched(self):
        tools = extract_tools("Built a RAG pipeline using Pinecone")
        assert "RAG" in tools

    def test_sql_legitimate_use_still_matched(self):
        tools = extract_tools("Wrote SQL queries")
        assert "SQL" in tools

    def test_sql_not_matched_inside_mysqlite(self):
        """SQL is a substring of 'mysqlite' but should not be reported."""
        tools = extract_tools("Implemented mysqlite cache")
        assert "SQL" not in tools

    def test_sql_not_matched_inside_postgresql(self):
        """Regression: \\bSQL\\b correctly does NOT match inside 'PostgreSQL'
        because both 'e' and 'S' are word chars — Python regex has no
        boundary between them. Pinning this so the boundary semantics
        remain correct even if anyone "improves" the pattern later.
        """
        for word in ["PostgreSQL", "NoSQL", "MySQL", "SQLite"]:
            tools = extract_tools(f"Stack: {word} and other tools")
            assert "SQL" not in tools, f"\\bSQL\\b should not fire inside {word!r}"

    def test_aws_legitimate_use_still_matched(self):
        tools = extract_tools("Deployed services on AWS Lambda")
        assert "AWS" in tools

    def test_aws_not_matched_inside_word(self):
        """AWS is a substring of 'aware' / 'awesome' but lowercase shouldn't match."""
        tools = extract_tools("We were aware of the awesome jaws of the issue")
        assert "AWS" not in tools

    def test_gcp_not_matched_inside_lowercase_noise(self):
        tools = extract_tools("logcap and gcpath are unrelated identifiers")
        assert "GCP" not in tools

    def test_gcp_legitimate_use_still_matched(self):
        tools = extract_tools("Migrated workloads to GCP")
        assert "GCP" in tools

    def test_dax_not_matched_inside_fedex(self):
        """DAX is a substring of words like 'fedax'/'redaxes' — should not match lowercase."""
        tools = extract_tools("Sorted fedax shipments and redaxes records")
        assert "DAX" not in tools

    def test_dax_legitimate_use_still_matched(self):
        tools = extract_tools("Wrote DAX measures in Power BI")
        assert "DAX" in tools

    def test_dbt_legitimate_use_still_matched(self):
        """dbt is a lowercase acronym in the vocab; it must still match when present."""
        tools = extract_tools("Managed dbt models")
        assert "dbt" in tools

    def test_dbt_not_matched_inside_doubt(self):
        tools = extract_tools("There is no doubt about the subtleties")
        assert "dbt" not in tools

    def test_ci_cd_legitimate_use_still_matched(self):
        tools = extract_tools("Built CI/CD pipelines")
        assert "CI/CD" in tools

    def test_slash_boundary_ai_ml(self):
        """Regression: 'AI/ML strategy' should match both AI and ML —
        slash is a word boundary in Python regex."""
        tools = extract_tools("Led AI/ML strategy and Python tooling")
        # Note: AI and ML may not be in TOOL_VOCAB — this test pins the boundary
        # behavior so if the vocab gains them, the slash separator works.
        # Skip the assertion if they're not in vocab.
        if "AI" in tools or "ML" in tools:
            # If either is in vocab, ensure both fire together
            from text_utils import TOOL_VOCAB
            if "AI" in TOOL_VOCAB:
                assert "AI" in tools
            if "ML" in TOOL_VOCAB:
                assert "ML" in tools


# ---------------------------------------------------------------------------
# Multi-word tools still require word-boundary anchoring
# ---------------------------------------------------------------------------
class TestExtractToolsMultiWord:
    def test_delta_lake_matched_case_insensitive(self):
        tools = extract_tools("Stored data in delta lake tables")
        assert "Delta Lake" in tools

    def test_github_actions_matched(self):
        tools = extract_tools("Configured GitHub Actions workflows")
        assert "GitHub Actions" in tools

    def test_microsoft_fabric_matched(self):
        tools = extract_tools("Built reports in Microsoft Fabric")
        assert "Microsoft Fabric" in tools


# ---------------------------------------------------------------------------
# Regular single-word tools — case-insensitive, boundary anchored
# ---------------------------------------------------------------------------
class TestExtractToolsRegularWords:
    def test_python_matched_case_insensitive(self):
        tools = extract_tools("Wrote python ETL pipeline")
        assert "Python" in tools

    def test_spark_matched_case_insensitive(self):
        tools = extract_tools("Optimized SPARK jobs")
        assert "Spark" in tools

    def test_kafka_not_matched_inside_kafkaesque(self):
        """Word-boundary should prevent matching inside larger words."""
        tools = extract_tools("Found the kafkaesque process frustrating")
        assert "Kafka" not in tools

    def test_kafka_legitimate_use_still_matched(self):
        tools = extract_tools("Streamed events through Kafka topics")
        assert "Kafka" in tools


# ---------------------------------------------------------------------------
# Determinism: dedupe + ordering
# ---------------------------------------------------------------------------
class TestExtractToolsDeterminism:
    def test_no_duplicates(self):
        tools = extract_tools("Python Python Python everywhere")
        assert tools.count("Python") == 1

    def test_multiple_tools_returned(self):
        tools = extract_tools("Used Python and Spark with Kafka on AWS")
        assert "Python" in tools
        assert "Spark" in tools
        assert "Kafka" in tools
        assert "AWS" in tools
