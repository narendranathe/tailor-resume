"""Tests for mcp_server.py — all four MCP tools, validation, and error paths."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude/skills/tailor-resume/scripts"))

from mcp_server import analyze_gap, extract_profile, render_latex, run_pipeline

FIXTURES = Path(__file__).parent.parent / "fixtures"
JD_TEXT = (FIXTURES / "sample_jd.txt").read_text(encoding="utf-8")
BLOB_TEXT = (FIXTURES / "sample_blob.txt").read_text(encoding="utf-8")
PROFILE_JSON = (FIXTURES / "sample_profile.json").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# extract_profile
# ---------------------------------------------------------------------------
class TestExtractProfile:
    def test_blob_returns_profile_with_experience(self):
        result = json.loads(extract_profile(BLOB_TEXT, format="blob"))
        assert "error" not in result
        assert len(result["experience"]) >= 1

    def test_markdown_format_accepted(self):
        md = "## Experience\n**DE** | Acme | 2022\n- Built pipelines\n"
        result = json.loads(extract_profile(md, format="markdown"))
        assert "error" not in result
        assert "experience" in result

    def test_latex_format_accepted(self):
        latex = r"\section{Experience}" + "\n" + r"\resumeSubheading{DE}{2022}{Acme}{Remote}"
        result = json.loads(extract_profile(latex, format="latex"))
        assert "error" not in result

    def test_linkedin_format_accepted(self):
        result = json.loads(extract_profile(BLOB_TEXT, format="linkedin"))
        assert "error" not in result

    def test_empty_text_returns_error(self):
        result = json.loads(extract_profile(""))
        assert "error" in result
        assert "empty" in result["error"]

    def test_whitespace_only_returns_error(self):
        result = json.loads(extract_profile("   \n\t  "))
        assert "error" in result

    def test_unknown_format_returns_error(self):
        result = json.loads(extract_profile("some text", format="pdf"))
        assert "error" in result
        assert "pdf" in result["error"]

    def test_result_has_all_profile_keys(self):
        result = json.loads(extract_profile(BLOB_TEXT))
        for key in ("experience", "projects", "skills", "education", "certifications"):
            assert key in result


# ---------------------------------------------------------------------------
# analyze_gap
# ---------------------------------------------------------------------------
class TestAnalyzeGap:
    def test_returns_gap_report(self):
        result = json.loads(analyze_gap(JD_TEXT, BLOB_TEXT))
        assert "error" not in result
        assert "ats_score_estimate" in result
        assert "top_missing" in result
        assert "recommendations" in result

    def test_ats_score_in_range(self):
        result = json.loads(analyze_gap(JD_TEXT, BLOB_TEXT))
        assert 0 <= result["ats_score_estimate"] <= 100

    def test_accepts_json_profile_as_resume_text(self):
        result = json.loads(analyze_gap(JD_TEXT, PROFILE_JSON))
        assert "error" not in result
        assert "ats_score_estimate" in result

    def test_top_n_respected(self):
        result = json.loads(analyze_gap(JD_TEXT, BLOB_TEXT, top_n=2))
        assert len(result["top_missing"]) <= 2

    def test_empty_jd_returns_error(self):
        result = json.loads(analyze_gap("", BLOB_TEXT))
        assert "error" in result
        assert "jd_text" in result["error"]

    def test_empty_resume_returns_error(self):
        result = json.loads(analyze_gap(JD_TEXT, ""))
        assert "error" in result
        assert "resume_text" in result["error"]

    def test_whitespace_jd_returns_error(self):
        result = json.loads(analyze_gap("   ", BLOB_TEXT))
        assert "error" in result


# ---------------------------------------------------------------------------
# render_latex
# ---------------------------------------------------------------------------
class TestRenderLatex:
    def test_renders_to_tex_file(self, tmp_path):
        output = str(tmp_path / "resume.tex")
        result = json.loads(render_latex(PROFILE_JSON, output_path=output, name="Jane"))
        assert "error" not in result
        assert Path(result["output_path"]).exists()

    def test_output_path_in_result(self, tmp_path):
        output = str(tmp_path / "out.tex")
        result = json.loads(render_latex(PROFILE_JSON, output_path=output))
        assert "output_path" in result
        assert result["output_path"].endswith(".tex")

    def test_name_injected(self, tmp_path):
        output = str(tmp_path / "resume.tex")
        render_latex(PROFILE_JSON, output_path=output, name="Test Person")
        content = Path(output).read_text(encoding="utf-8")
        assert "Test Person" in content

    def test_empty_profile_json_returns_error(self):
        result = json.loads(render_latex(""))
        assert "error" in result

    def test_invalid_json_returns_error(self):
        result = json.loads(render_latex("this is not json"))
        assert "error" in result
        assert "json" in result["error"].lower() or "invalid" in result["error"].lower()

    def test_result_has_message(self, tmp_path):
        output = str(tmp_path / "resume.tex")
        result = json.loads(render_latex(PROFILE_JSON, output_path=output))
        assert "message" in result


# ---------------------------------------------------------------------------
# run_pipeline
# ---------------------------------------------------------------------------
class TestRunPipeline:
    def test_full_pipeline_returns_all_keys(self, tmp_path):
        output = str(tmp_path / "resume.tex")
        result = json.loads(run_pipeline(
            jd_text=JD_TEXT,
            artifact_text=BLOB_TEXT,
            output_path=output,
            name="Jane",
            email="jane@example.com",
        ))
        assert "error" not in result
        assert "profile" in result
        assert "gap_report" in result
        assert "output_path" in result

    def test_output_file_created(self, tmp_path):
        output = str(tmp_path / "resume.tex")
        result = json.loads(run_pipeline(JD_TEXT, BLOB_TEXT, output_path=output))
        assert Path(result["output_path"]).exists()

    def test_gap_report_has_ats_score(self, tmp_path):
        output = str(tmp_path / "resume.tex")
        result = json.loads(run_pipeline(JD_TEXT, BLOB_TEXT, output_path=output))
        assert "ats_score_estimate" in result["gap_report"]

    def test_empty_jd_returns_error(self):
        result = json.loads(run_pipeline("", BLOB_TEXT))
        assert "error" in result

    def test_empty_artifact_returns_error(self):
        result = json.loads(run_pipeline(JD_TEXT, ""))
        assert "error" in result

    def test_unknown_format_returns_error(self):
        result = json.loads(run_pipeline(JD_TEXT, BLOB_TEXT, artifact_format="pdf"))
        assert "error" in result
        assert "pdf" in result["error"]

    def test_top_gaps_respected(self, tmp_path):
        output = str(tmp_path / "resume.tex")
        result = json.loads(run_pipeline(JD_TEXT, BLOB_TEXT, output_path=output, top_gaps=2))
        assert len(result["gap_report"]["top_missing"]) <= 2
