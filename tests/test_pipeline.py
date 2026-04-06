"""Tests for pipeline.py — execute_text() and core pipeline logic."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude/skills/tailor-resume/scripts"))

FIXTURES = Path(__file__).parent.parent / "fixtures"
JD_TEXT = (FIXTURES / "sample_jd.txt").read_text(encoding="utf-8")
BLOB_TEXT = (FIXTURES / "sample_blob.txt").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# execute_text
# ---------------------------------------------------------------------------
class TestExecuteText:
    def test_returns_tailor_result(self, tmp_path):
        from pipeline import TailorResult, execute_text
        result = execute_text(
            jd_text=JD_TEXT,
            artifact_text=BLOB_TEXT,
            artifact_format="blob",
            output_path=str(tmp_path / "resume.tex"),
        )
        assert isinstance(result, TailorResult)

    def test_output_file_created(self, tmp_path):
        from pipeline import execute_text
        out = tmp_path / "resume.tex"
        execute_text(JD_TEXT, BLOB_TEXT, output_path=str(out))
        assert out.exists()

    def test_ats_score_in_range(self, tmp_path):
        from pipeline import execute_text
        result = execute_text(JD_TEXT, BLOB_TEXT, output_path=str(tmp_path / "r.tex"))
        assert 0 <= result.ats_score <= 100

    def test_gap_summary_has_ats_line(self, tmp_path):
        from pipeline import execute_text
        result = execute_text(JD_TEXT, BLOB_TEXT, output_path=str(tmp_path / "r.tex"))
        assert any("ATS Score" in line for line in result.gap_summary)

    def test_profile_dict_has_experience(self, tmp_path):
        from pipeline import execute_text
        result = execute_text(JD_TEXT, BLOB_TEXT, output_path=str(tmp_path / "r.tex"))
        assert "experience" in result.profile_dict

    def test_markdown_format_works(self, tmp_path):
        from pipeline import execute_text
        md = "## Experience\n**Data Engineer** | Acme | 2022 - Present\n- Reduced ETL 73%.\n"
        result = execute_text(JD_TEXT, md, artifact_format="markdown",
                              output_path=str(tmp_path / "r.tex"))
        assert result.ats_score >= 0

    def test_unknown_format_raises(self, tmp_path):
        from pipeline import execute_text
        with pytest.raises(ValueError, match="Unknown artifact format"):
            execute_text(JD_TEXT, BLOB_TEXT, artifact_format="pdf",
                         output_path=str(tmp_path / "r.tex"))

    def test_empty_artifacts_does_not_raise_for_execute_text(self, tmp_path):
        # execute_text with empty string still parses (returns empty profile)
        from pipeline import execute_text
        result = execute_text(JD_TEXT, "no roles here",
                              output_path=str(tmp_path / "r.tex"))
        assert isinstance(result.profile_dict, dict)

    def test_user_id_echoed_in_result(self, tmp_path):
        from pipeline import execute_text
        result = execute_text(JD_TEXT, BLOB_TEXT, output_path=str(tmp_path / "r.tex"),
                              user_id="test-user-42")
        assert result.user_id == "test-user-42"

    def test_top_gaps_limits_report(self, tmp_path):
        from pipeline import execute_text
        result = execute_text(JD_TEXT, BLOB_TEXT, output_path=str(tmp_path / "r.tex"),
                              top_gaps=2)
        assert len(result.report.top_missing) <= 2

    def test_report_is_gap_report_instance(self, tmp_path):
        from pipeline import execute_text
        from resume_types import GapReport
        result = execute_text(JD_TEXT, BLOB_TEXT, output_path=str(tmp_path / "r.tex"))
        assert isinstance(result.report, GapReport)

    def test_cover_letter_false_by_default(self, tmp_path):
        from pipeline import execute_text
        result = execute_text(JD_TEXT, BLOB_TEXT, output_path=str(tmp_path / "r.tex"))
        assert result.cover_letter_tex is None
        assert result.cover_letter_path is None


# ---------------------------------------------------------------------------
# TailorConfig / TailorResult data classes
# ---------------------------------------------------------------------------
class TestTailorConfig:
    def test_default_user_id_is_empty(self):
        from pipeline import TailorConfig
        config = TailorConfig(
            jd_text="jd", artifacts=[("f.txt", "blob")], output_path="out/r.tex"
        )
        assert config.user_id == ""

    def test_cover_letter_defaults_false(self):
        from pipeline import TailorConfig
        config = TailorConfig(jd_text="jd", artifacts=[], output_path="out/r.tex")
        assert config.cover_letter is False


class TestTailorResult:
    def test_user_id_defaults_empty(self):
        from pipeline import TailorResult
        r = TailorResult(output_path="r.tex", ats_score=70, gap_summary=[], profile_dict={})
        assert r.user_id == ""

    def test_cover_letter_fields_default_none(self):
        from pipeline import TailorResult
        r = TailorResult(output_path="r.tex", ats_score=70, gap_summary=[], profile_dict={})
        assert r.cover_letter_tex is None
        assert r.cover_letter_path is None
