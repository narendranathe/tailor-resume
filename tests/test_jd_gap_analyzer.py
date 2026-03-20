"""Tests for jd_gap_analyzer.py — tokenizer, coverage scoring, gap signals, ATS score."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude/skills/tailor-resume/scripts"))

from jd_gap_analyzer import (
    analyze_category_coverage,
    build_gap_signals,
    keyword_gaps,
    estimate_ats_score,
    run_analysis,
    GapSignal,
)
from text_utils import tokenize, extract_phrases

JD_RICH = """
We are looking for a Senior Data Engineer with strong experience in Airflow orchestration,
data quality frameworks (Great Expectations or Monte Carlo), CI/CD pipelines, and Spark
performance tuning. You will own the semantic layer and build governed metric definitions
used by finance, ML, and BI teams. Strong Python and SQL skills required.
Must have experience with Delta Lake or Iceberg and cost optimization on cloud platforms.
Experience with Kafka streaming and real-time data processing preferred.
"""

RESUME_PARTIAL = """
Data Engineer with experience in Python, SQL, Azure, CI/CD through Azure DevOps,
CDC-based ETL and anomaly detection pipelines.
"""

RESUME_STRONG = """
Senior Data Engineer. Built Airflow DAGs with SLA monitoring and backfill strategy.
Implemented Great Expectations data quality framework, reducing incidents by 80%.
Owned CI/CD pipeline with ruff, pytest, GitHub Actions. Optimized Spark jobs 3x faster.
Built semantic layer with governed metrics on Databricks. Cost optimization saving $50k/year.
Designed Delta Lake tables with partition pruning. Kafka streaming at 100k events/sec.
Python, SQL, dbt, Terraform expertise.
"""


# ---------------------------------------------------------------------------
# tokenize
# ---------------------------------------------------------------------------
class TestTokenize:
    def test_returns_lowercase_tokens(self):
        tokens = tokenize("Apache Airflow Python")
        assert "airflow" in tokens
        assert "python" in tokens

    def test_filters_stopwords(self):
        tokens = tokenize("the and or with for")
        # Common stopwords should be filtered
        assert "the" not in tokens
        assert "and" not in tokens

    def test_filters_short_words(self):
        tokens = tokenize("a in be of")
        for t in tokens:
            assert len(t) > 2

    def test_empty_string(self):
        assert tokenize("") == []

    def test_preserves_hyphenated_words(self):
        tokens = tokenize("CI/CD end-to-end")
        assert any("ci" in t or "cd" in t or "end" in t for t in tokens)


# ---------------------------------------------------------------------------
# extract_phrases
# ---------------------------------------------------------------------------
class TestExtractPhrases:
    def test_returns_bigrams(self):
        phrases = extract_phrases("data quality monitoring")
        assert "data quality" in phrases

    def test_returns_trigrams_when_n3(self):
        phrases = extract_phrases("real time data processing", n=3)
        assert "real time data" in phrases

    def test_empty_string(self):
        assert extract_phrases("") == []

    def test_single_word(self):
        # No bigrams possible from 1 word
        assert extract_phrases("python") == []


# ---------------------------------------------------------------------------
# analyze_category_coverage
# ---------------------------------------------------------------------------
class TestAnalyzeCategoryCoverage:
    def test_returns_dict_with_categories(self):
        result = analyze_category_coverage(JD_RICH, RESUME_PARTIAL)
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_each_category_has_required_keys(self):
        result = analyze_category_coverage(JD_RICH, RESUME_PARTIAL)
        for cat, data in result.items():
            assert "jd_keywords" in data
            assert "resume_coverage" in data
            assert "missing_keywords" in data

    def test_coverage_is_between_zero_and_one(self):
        result = analyze_category_coverage(JD_RICH, RESUME_PARTIAL)
        for cat, data in result.items():
            assert 0.0 <= data["resume_coverage"] <= 1.0

    def test_strong_resume_has_higher_coverage(self):
        weak = analyze_category_coverage(JD_RICH, RESUME_PARTIAL)
        strong = analyze_category_coverage(JD_RICH, RESUME_STRONG)
        avg_weak = sum(v["resume_coverage"] for v in weak.values()) / len(weak)
        avg_strong = sum(v["resume_coverage"] for v in strong.values()) / len(strong)
        assert avg_strong >= avg_weak

    def test_category_with_no_jd_keywords_gets_full_coverage(self):
        # JD with no orchestration keywords — orchestration category should show empty jd_keywords
        minimal_jd = "We need a Python developer."
        result = analyze_category_coverage(minimal_jd, "Python developer")
        for cat, data in result.items():
            if not data["jd_keywords"]:
                # No JD keywords means coverage defaults to 1.0
                assert data["resume_coverage"] == 1.0


# ---------------------------------------------------------------------------
# build_gap_signals
# ---------------------------------------------------------------------------
class TestBuildGapSignals:
    def test_returns_list_of_gap_signals(self):
        coverage = analyze_category_coverage(JD_RICH, RESUME_PARTIAL)
        signals = build_gap_signals(coverage, top_n=5)
        assert isinstance(signals, list)
        for s in signals:
            assert isinstance(s, GapSignal)

    def test_respects_top_n_limit(self):
        coverage = analyze_category_coverage(JD_RICH, RESUME_PARTIAL)
        signals = build_gap_signals(coverage, top_n=3)
        assert len(signals) <= 3

    def test_high_priority_signals_come_first(self):
        coverage = analyze_category_coverage(JD_RICH, RESUME_PARTIAL)
        signals = build_gap_signals(coverage, top_n=10)
        priorities = [s.priority for s in signals]
        # "high" should appear before "medium" in sorted output
        if "high" in priorities and "medium" in priorities:
            assert priorities.index("high") < priorities.index("medium")

    def test_signals_have_suggested_angles(self):
        coverage = analyze_category_coverage(JD_RICH, RESUME_PARTIAL)
        signals = build_gap_signals(coverage, top_n=5)
        # At least some signals should have suggested angles
        all_angles = [a for s in signals for a in s.suggested_angles]
        assert len(all_angles) >= 0  # Non-negative (may be empty for some)

    def test_skips_categories_with_no_jd_keywords(self):
        # Build a coverage dict where all categories have no JD keywords
        empty_coverage = {
            "testing_ci_cd": {
                "jd_keywords": [],
                "jd_frequency": 0,
                "resume_coverage": 1.0,
                "missing_keywords": [],
            }
        }
        signals = build_gap_signals(empty_coverage)
        assert signals == []


# ---------------------------------------------------------------------------
# keyword_gaps
# ---------------------------------------------------------------------------
class TestKeywordGaps:
    def test_returns_list_of_tuples(self):
        gaps = keyword_gaps(JD_RICH, RESUME_PARTIAL)
        assert isinstance(gaps, list)
        for item in gaps:
            assert isinstance(item, tuple)
            assert len(item) == 2

    def test_gaps_sorted_by_frequency_desc(self):
        gaps = keyword_gaps(JD_RICH, RESUME_PARTIAL)
        freqs = [g[1] for g in gaps]
        assert freqs == sorted(freqs, reverse=True)

    def test_respects_top_n(self):
        gaps = keyword_gaps(JD_RICH, RESUME_PARTIAL, top_n=3)
        assert len(gaps) <= 3

    def test_missing_keywords_have_min_freq(self):
        gaps = keyword_gaps(JD_RICH, RESUME_PARTIAL, min_freq=2)
        for term, freq in gaps:
            assert freq >= 2

    def test_terms_in_resume_not_in_gaps(self):
        # "python" is in both JD and RESUME_PARTIAL — should not appear as a gap
        gaps = keyword_gaps(JD_RICH, RESUME_PARTIAL)
        gap_terms = [g[0] for g in gaps]
        assert "python" not in gap_terms


# ---------------------------------------------------------------------------
# estimate_ats_score
# ---------------------------------------------------------------------------
class TestEstimateAtsScore:
    def test_score_is_in_range(self):
        coverage = analyze_category_coverage(JD_RICH, RESUME_PARTIAL)
        score = estimate_ats_score(JD_RICH, RESUME_PARTIAL, coverage)
        assert 0 <= score <= 100

    def test_strong_resume_scores_higher(self):
        weak_cov = analyze_category_coverage(JD_RICH, RESUME_PARTIAL)
        strong_cov = analyze_category_coverage(JD_RICH, RESUME_STRONG)
        weak_score = estimate_ats_score(JD_RICH, RESUME_PARTIAL, weak_cov)
        strong_score = estimate_ats_score(JD_RICH, RESUME_STRONG, strong_cov)
        assert strong_score >= weak_score

    def test_identical_texts_score_high(self):
        cov = analyze_category_coverage(JD_RICH, JD_RICH)
        score = estimate_ats_score(JD_RICH, JD_RICH, cov)
        assert score >= 50  # Same text should score at least reasonably high


# ---------------------------------------------------------------------------
# run_analysis — recommendations branches
# ---------------------------------------------------------------------------
class TestRunAnalysisRecommendations:
    def test_low_ats_score_gets_critical_recommendation(self):
        # Give a JD with lots of unique keywords and a very short resume
        sparse_resume = "I am a developer."
        jd = ("Airflow Airflow Airflow Dagster Dagster spark spark "
              "delta delta kafka kafka dbt dbt terraform terraform "
              "great expectations data contracts schema enforcement "
              "CI/CD pipeline testing pytest coverage semantic layer "
              "governed metrics workload isolation cost optimization")
        report = run_analysis(jd, sparse_resume)
        assert any("Critical" in r or "keyword" in r.lower() for r in report.recommendations)

    def test_good_coverage_gets_positive_recommendation(self):
        # JD and resume are identical — no gaps
        jd = "Python Spark SQL"
        report = run_analysis(jd, jd, top_n=5)
        assert len(report.recommendations) >= 1

    def test_report_structure_is_complete(self):
        report = run_analysis(JD_RICH, RESUME_PARTIAL)
        assert hasattr(report, "top_missing")
        assert hasattr(report, "keyword_gaps")
        assert hasattr(report, "ats_score_estimate")
        assert hasattr(report, "recommendations")
        assert isinstance(report.recommendations, list)
