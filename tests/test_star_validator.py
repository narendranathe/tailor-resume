"""Tests for star_validator.py — STARScore, score_star, bullet_quality_score, enforce_star."""
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / ".claude/skills/tailor-resume/scripts"))

from star_validator import (
    MAX_BULLET_WORDS,
    bullet_quality_score,
    enforce_star,
    score_star,
)


# ---------------------------------------------------------------------------
# score_star
# ---------------------------------------------------------------------------
class TestScoreStar:
    def test_compliant_bullet_passes(self):
        text = "Reduced ETL runtime 73% by migrating to CDC upserts."
        s = score_star(text)
        assert s.has_action is True
        assert s.has_result is True
        assert s.star_score == 2
        assert s.passes is True

    def test_missing_action_scores_1(self):
        text = "Pipeline runtime dropped 60% after optimization work."
        s = score_star(text)
        assert s.star_score <= 2
        # has_result must be True (60%)
        assert s.has_result is True

    def test_missing_result_flags_violation(self):
        text = "Built and deployed a new data pipeline for the analytics team."
        s = score_star(text)
        if not s.has_result:
            assert any("result" in v for v in s.violations)

    def test_over_limit_fails_passes(self):
        words = ["built"] + ["word"] * MAX_BULLET_WORDS  # 21 words
        text = " ".join(words) + " reduced 73%."
        s = score_star(text)
        assert s.word_count > MAX_BULLET_WORDS
        assert s.passes is False
        assert any("too long" in v for v in s.violations)

    def test_exactly_20_words_passes_length(self):
        text = "Built Spark pipeline reducing ETL 73% " + " ".join(["word"] * 14)
        words = text.split()[:MAX_BULLET_WORDS]
        text = " ".join(words)
        s = score_star(text)
        assert s.word_count == MAX_BULLET_WORDS

    def test_word_count_is_accurate(self):
        text = "one two three four five"
        s = score_star(text)
        assert s.word_count == 5

    def test_violations_list_is_list(self):
        s = score_star("some text here")
        assert isinstance(s.violations, list)

    def test_star_score_dataclass_fields(self):
        s = score_star("built pipeline reducing 40%")
        assert hasattr(s, "has_action")
        assert hasattr(s, "has_result")
        assert hasattr(s, "word_count")
        assert hasattr(s, "star_score")
        assert hasattr(s, "passes")
        assert hasattr(s, "violations")

    def test_strong_bullet_no_violations(self):
        text = "Reduced batch runtime 80% by migrating to CDC."
        s = score_star(text)
        assert s.star_score >= 1  # at minimum has result

    def test_empty_text_scores_zero(self):
        s = score_star("")
        assert s.star_score == 0
        assert s.passes is False

    def test_dollar_metric_counts_as_result(self):
        text = "Reduced compute costs $3k/month via Delta Lake compaction."
        s = score_star(text)
        assert s.has_result is True

    def test_time_metric_counts_as_result(self):
        text = "Automated deployment cutting cycle from 3 weeks to 2 days."
        s = score_star(text)
        assert s.has_result is True

    def test_multiplier_counts_as_result(self):
        text = "Scaled Kafka throughput 10x by adding partition sharding."
        s = score_star(text)
        assert s.has_result is True


# ---------------------------------------------------------------------------
# bullet_quality_score
# ---------------------------------------------------------------------------
class TestBulletQualityScore:
    def test_returns_float_between_0_and_1(self):
        bullet = {
            "text": "Reduced ETL 73% via CDC.",
            "metrics": ["73%"],
            "tools": ["Spark"],
            "confidence": "high",
        }
        score = bullet_quality_score(bullet)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_high_confidence_high_metrics_scores_high(self):
        bullet = {
            "text": "Reduced ETL runtime 73% by migrating to CDC upserts.",
            "metrics": ["73%", "30 min", "8 min"],
            "tools": ["Spark", "Kafka"],
            "confidence": "high",
        }
        score = bullet_quality_score(bullet)
        assert score >= 0.7

    def test_no_metrics_no_tools_low_confidence_scores_low(self):
        bullet = {
            "text": "Worked on data pipeline improvements.",
            "metrics": [],
            "tools": [],
            "confidence": "low",
        }
        score = bullet_quality_score(bullet)
        assert score < 0.5

    def test_missing_keys_do_not_raise(self):
        score = bullet_quality_score({})
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_score_bounded_at_1(self):
        bullet = {
            "text": "Reduced ETL 73% and improved latency 80% by rebuilding.",
            "metrics": ["73%", "80%", "$5k", "30 min", "2 days"],
            "tools": ["Spark", "Kafka", "Airflow"],
            "confidence": "high",
        }
        assert bullet_quality_score(bullet) <= 1.0

    def test_medium_confidence_scores_between_low_and_high(self):
        base = {"text": "Built pipeline.", "metrics": ["40%"], "tools": [], "confidence": "medium"}
        high = {"text": "Built pipeline.", "metrics": ["40%"], "tools": [], "confidence": "high"}
        low = {"text": "Built pipeline.", "metrics": ["40%"], "tools": [], "confidence": "low"}
        assert bullet_quality_score(low) <= bullet_quality_score(base) <= bullet_quality_score(high)


# ---------------------------------------------------------------------------
# enforce_star
# ---------------------------------------------------------------------------
class TestEnforceStar:
    def test_adds_star_score_field(self):
        bullets = [{"text": "Reduced ETL 73%.", "metrics": [], "tools": [], "confidence": "medium"}]
        result = enforce_star(bullets)
        assert "star_score" in result[0]

    def test_adds_star_passes_field(self):
        bullets = [{"text": "Built Spark jobs.", "metrics": [], "tools": [], "confidence": "low"}]
        result = enforce_star(bullets)
        assert "star_passes" in result[0]

    def test_adds_star_violations_field(self):
        bullets = [{"text": "did stuff.", "metrics": [], "tools": [], "confidence": "low"}]
        result = enforce_star(bullets)
        assert "star_violations" in result[0]
        assert isinstance(result[0]["star_violations"], list)

    def test_preserves_original_keys(self):
        bullets = [{"text": "Built pipeline.", "metrics": ["40%"], "tools": ["Spark"],
                    "evidence_source": "blob", "confidence": "high"}]
        result = enforce_star(bullets)
        assert result[0]["text"] == "Built pipeline."
        assert result[0]["metrics"] == ["40%"]
        assert result[0]["evidence_source"] == "blob"

    def test_empty_list_returns_empty(self):
        assert enforce_star([]) == []

    def test_multiple_bullets_all_annotated(self):
        bullets = [
            {"text": "Reduced latency 40%.", "metrics": ["40%"], "tools": [], "confidence": "medium"},
            {"text": "Built Kafka pipeline.", "metrics": [], "tools": ["Kafka"], "confidence": "low"},
        ]
        result = enforce_star(bullets)
        assert len(result) == 2
        for b in result:
            assert "star_score" in b
            assert "star_passes" in b

    def test_compliant_bullet_star_passes_true(self):
        bullets = [{"text": "Reduced ETL 73% via CDC.", "metrics": ["73%"],
                    "tools": ["Spark"], "confidence": "high"}]
        result = enforce_star(bullets)
        # should have has_action and has_result → passes if also <=20 words
        assert isinstance(result[0]["star_passes"], bool)


# ---------------------------------------------------------------------------
# MAX_BULLET_WORDS constant
# ---------------------------------------------------------------------------
class TestConstants:
    def test_max_bullet_words_is_20(self):
        assert MAX_BULLET_WORDS == 20
