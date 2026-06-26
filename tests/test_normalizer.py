"""Tests for parsers/normalizer.py — date normalization, dedup, format detection."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude/skills/tailor-resume/scripts"))

from parsers.normalizer import (
    _dedupe,
    _normalize_date_token,
    _parse_dates,
    auto_detect_format,
    merge_profiles,
)
from resume_types import Profile, Role, Bullet


# ---------------------------------------------------------------------------
# _dedupe
# ---------------------------------------------------------------------------
class TestDedupe:
    def test_removes_case_duplicates(self):
        assert _dedupe(["Python", "python", "PYTHON"]) == ["Python"]

    def test_preserves_first_seen_casing(self):
        assert _dedupe(["SQL", "sql"]) == ["SQL"]

    def test_empty_list(self):
        assert _dedupe([]) == []

    def test_no_duplicates_unchanged(self):
        result = _dedupe(["Python", "Spark", "Kafka"])
        assert result == ["Python", "Spark", "Kafka"]

    def test_strips_whitespace_before_comparing(self):
        assert _dedupe(["Python ", "Python"]) == ["Python "]


# ---------------------------------------------------------------------------
# _normalize_date_token
# ---------------------------------------------------------------------------
class TestNormalizeDateToken:
    def test_slash_date(self):
        assert _normalize_date_token("07/2024") == "Jul 2024"

    def test_slash_date_january(self):
        assert _normalize_date_token("01/2022") == "Jan 2022"

    def test_iso_date(self):
        assert _normalize_date_token("2024-07") == "Jul 2024"

    def test_iso_date_december(self):
        assert _normalize_date_token("2023-12") == "Dec 2023"

    def test_full_month_name(self):
        assert _normalize_date_token("July 2024") == "Jul 2024"

    def test_abbreviated_month(self):
        assert _normalize_date_token("Aug. 2023") == "Aug 2023"

    def test_present(self):
        assert _normalize_date_token("Present") == "Present"

    def test_current(self):
        assert _normalize_date_token("Current") == "Present"

    def test_now(self):
        assert _normalize_date_token("Now") == "Present"

    def test_present_case_insensitive(self):
        assert _normalize_date_token("PRESENT") == "Present"

    def test_passthrough_unknown(self):
        assert _normalize_date_token("Spring 2022") == "Spring 2022"

    def test_empty_string(self):
        assert _normalize_date_token("") == ""

    def test_out_of_range_month_slash(self):
        assert _normalize_date_token("13/2024") == "13/2024"

    def test_out_of_range_month_iso(self):
        assert _normalize_date_token("2024-13") == "2024-13"

    def test_january_full(self):
        assert _normalize_date_token("January 2022") == "Jan 2022"

    def test_september_abbreviated(self):
        assert _normalize_date_token("Sep 2021") == "Sep 2021"

    def test_september_full(self):
        assert _normalize_date_token("September 2021") == "Sep 2021"


# ---------------------------------------------------------------------------
# _parse_dates
# ---------------------------------------------------------------------------
class TestParseDates:
    def test_en_dash_separator(self):
        start, end = _parse_dates("Jan 2022 – Dec 2023")
        assert start == "Jan 2022"
        assert end == "Dec 2023"

    def test_double_dash_separator(self):
        start, end = _parse_dates("01/2022 -- Present")
        assert start == "Jan 2022"
        assert end == "Present"

    def test_normalizes_slash_date(self):
        start, end = _parse_dates("07/2024 – Present")
        assert start == "Jul 2024"
        assert end == "Present"

    def test_normalizes_iso_date(self):
        start, end = _parse_dates("2024-07 – 2025-01")
        assert start == "Jul 2024"
        assert end == "Jan 2025"

    def test_single_token(self):
        start, end = _parse_dates("Jul 2024")
        assert start == "Jul 2024"
        assert end == ""

    def test_present_both_sides(self):
        start, end = _parse_dates("Jan 2020 - Present")
        assert end == "Present"


# ---------------------------------------------------------------------------
# auto_detect_format
# ---------------------------------------------------------------------------
class TestAutoDetectFormat:
    def test_detects_latex(self):
        assert auto_detect_format(r"\documentclass{article}") == "latex"

    def test_detects_resumeSubheading(self):
        assert auto_detect_format(r"\resumeSubheading{Acme}{}{}{}") == "latex"

    def test_detects_markdown(self):
        assert auto_detect_format("# Summary\n- Built stuff") == "markdown"

    def test_plain_blob(self):
        assert auto_detect_format("John Doe\nSoftware Engineer at Acme Corp") == "blob"


# ---------------------------------------------------------------------------
# merge_profiles
# ---------------------------------------------------------------------------
class TestMergeProfiles:
    def test_merges_skills_deduped(self):
        p1 = Profile(skills=["Python", "Spark"])
        p2 = Profile(skills=["Python", "Kafka"])
        merged = merge_profiles(p1, p2)
        assert "Python" in merged.skills
        assert "Spark" in merged.skills
        assert "Kafka" in merged.skills
        assert merged.skills.count("Python") == 1

    def test_merges_experience(self):
        r1 = Role(title="DE", company="A", start="2022", end="2023", location="", bullets=[])
        r2 = Role(title="SWE", company="B", start="2021", end="2022", location="", bullets=[])
        p1 = Profile(experience=[r1])
        p2 = Profile(experience=[r2])
        merged = merge_profiles(p1, p2)
        assert len(merged.experience) == 2

    def test_empty_merge(self):
        merged = merge_profiles(Profile(), Profile())
        assert merged.skills == []
        assert merged.experience == []
