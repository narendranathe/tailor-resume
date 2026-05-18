"""Regression tests for text_utils.extract_metrics — Issue #112.

The pre-fix regex was too greedy and would capture entire sentence trailers
after numeric tokens (60+ characters of text). These tests pin the corrected
behaviour: each metric is a concise numeric phrase (cap 30 chars), and no
match crosses sentence/conjunction boundaries or other digit tokens.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude/skills/tailor-resume/scripts"))

from text_utils import extract_metrics  # noqa: E402


MAX_LEN = 30


def _no_trailers(metrics):
    assert all(len(m) <= MAX_LEN for m in metrics), (
        f"extract_metrics returned an over-long element: "
        f"{[m for m in metrics if len(m) > MAX_LEN]}"
    )


# ---------------------------------------------------------------------------
# Issue #112 — the original failing input
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
# Sanity — preserve previously expected behaviour
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
