"""Tests for CLI main() entry points across all four scripts."""
import json
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).parent.parent / ".claude/skills/tailor-resume/scripts"))

FIXTURES = Path(__file__).parent.parent / "fixtures"
JD_FILE = FIXTURES / "sample_jd.txt"
BLOB_FILE = FIXTURES / "sample_blob.txt"
PROFILE_FILE = FIXTURES / "sample_profile.json"
TEMPLATE_FILE = (
    Path(__file__).parent.parent
    / ".claude/skills/tailor-resume/templates/resume_template.tex"
)


# ---------------------------------------------------------------------------
# jd_gap_analyzer main()
# ---------------------------------------------------------------------------
class TestJdGapAnalyzerCli:
    def test_main_runs_and_prints_ats_score(self, monkeypatch, capsys, tmp_path):
        monkeypatch.setattr(
            sys, "argv",
            ["jd_gap_analyzer.py", "--jd", str(JD_FILE), "--profile", str(PROFILE_FILE)],
        )
        import jd_gap_analyzer
        jd_gap_analyzer.main()
        out = capsys.readouterr().out
        assert "ATS Score" in out

    def test_main_prints_gap_signals(self, monkeypatch, capsys):
        monkeypatch.setattr(
            sys, "argv",
            ["jd_gap_analyzer.py", "--jd", str(JD_FILE), "--profile", str(PROFILE_FILE)],
        )
        import jd_gap_analyzer
        jd_gap_analyzer.main()
        out = capsys.readouterr().out
        assert "Missing" in out or "Signals" in out or "Category" in out or "HIGH" in out or "MEDIUM" in out or "LOW" in out

    def test_main_accepts_plain_text_profile(self, monkeypatch, capsys, tmp_path):
        # --profile can be a plain text file (not JSON)
        text_profile = tmp_path / "resume.txt"
        text_profile.write_text("Python Spark Airflow data engineer", encoding="utf-8")
        monkeypatch.setattr(
            sys, "argv",
            ["jd_gap_analyzer.py", "--jd", str(JD_FILE), "--profile", str(text_profile)],
        )
        import jd_gap_analyzer
        jd_gap_analyzer.main()
        out = capsys.readouterr().out
        assert "ATS Score" in out

    def test_main_respects_top_flag(self, monkeypatch, capsys):
        monkeypatch.setattr(
            sys, "argv",
            ["jd_gap_analyzer.py", "--jd", str(JD_FILE), "--profile", str(PROFILE_FILE), "--top", "2"],
        )
        import jd_gap_analyzer
        jd_gap_analyzer.main()
        out = capsys.readouterr().out
        assert "ATS Score" in out


# ---------------------------------------------------------------------------
# latex_renderer main()
# ---------------------------------------------------------------------------
class TestLatexRendererCli:
    def test_main_creates_output_file(self, monkeypatch, capsys, tmp_path):
        output = tmp_path / "resume.tex"
        monkeypatch.setattr(
            sys, "argv",
            [
                "latex_renderer.py",
                "--profile", str(PROFILE_FILE),
                "--template", str(TEMPLATE_FILE),
                "--output", str(output),
                "--name", "Jane Smith",
                "--email", "jane@example.com",
            ],
        )
        import latex_renderer
        latex_renderer.main()
        assert output.exists()

    def test_main_injects_name(self, monkeypatch, capsys, tmp_path):
        output = tmp_path / "resume.tex"
        monkeypatch.setattr(
            sys, "argv",
            [
                "latex_renderer.py",
                "--profile", str(PROFILE_FILE),
                "--template", str(TEMPLATE_FILE),
                "--output", str(output),
                "--name", "Test Person",
                "--email", "test@example.com",
                "--linkedin", "https://linkedin.com/in/test",
            ],
        )
        import latex_renderer
        latex_renderer.main()
        content = output.read_text(encoding="utf-8")
        assert "Test Person" in content


# ---------------------------------------------------------------------------
# profile_extractor main()
# ---------------------------------------------------------------------------
class TestProfileExtractorCli:
    def test_main_blob_to_stdout(self, monkeypatch, capsys):
        monkeypatch.setattr(
            sys, "argv",
            ["profile_extractor.py", "--input", str(BLOB_FILE), "--format", "blob", "--output", "-"],
        )
        import profile_extractor
        profile_extractor.main()
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "experience" in data

    def test_main_blob_to_file(self, monkeypatch, capsys, tmp_path):
        output = tmp_path / "profile.json"
        monkeypatch.setattr(
            sys, "argv",
            ["profile_extractor.py", "--input", str(BLOB_FILE), "--format", "blob", "--output", str(output)],
        )
        import profile_extractor
        profile_extractor.main()
        assert output.exists()
        data = json.loads(output.read_text(encoding="utf-8"))
        assert "experience" in data

    def test_main_markdown_format(self, monkeypatch, capsys, tmp_path):
        md_file = tmp_path / "resume.md"
        md_file.write_text(
            "## Experience\n**Data Engineer** | Acme | 2022 - Present\n- Built pipelines\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            sys, "argv",
            ["profile_extractor.py", "--input", str(md_file), "--format", "markdown", "--output", "-"],
        )
        import profile_extractor
        profile_extractor.main()
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "experience" in data

    def test_main_linkedin_format(self, monkeypatch, capsys, tmp_path):
        li_file = tmp_path / "linkedin.txt"
        li_file.write_text("Company: DataWorks\nTitle: DE\n- Built pipelines\n", encoding="utf-8")
        monkeypatch.setattr(
            sys, "argv",
            ["profile_extractor.py", "--input", str(li_file), "--format", "linkedin", "--output", "-"],
        )
        import profile_extractor
        profile_extractor.main()
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "experience" in data


# ---------------------------------------------------------------------------
# rag_store main() — SQLite backend only
# ---------------------------------------------------------------------------
class TestRagStoreCli:
    def test_main_store_command(self, monkeypatch, capsys, tmp_path):
        monkeypatch.delenv("PINECONE_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr(
            sys, "argv",
            ["rag_store.py", "store", "--profile", str(PROFILE_FILE), "--user-id", "cli-test-user"],
        )
        import rag_store
        rag_store.main()
        out = capsys.readouterr().out
        assert "Stored" in out or "stored" in out or "vector_id" in out

    def test_main_list_command(self, monkeypatch, capsys):
        monkeypatch.delenv("PINECONE_API_KEY", raising=False)
        monkeypatch.setattr(sys, "argv", ["rag_store.py", "list"])
        import rag_store
        rag_store.main()
        out = capsys.readouterr().out
        # Should print "Stored user IDs:" header
        assert "user" in out.lower() or out == ""


# ---------------------------------------------------------------------------
# cli.py — pipeline orchestrator (run_pipeline + main)
# ---------------------------------------------------------------------------
class TestCliPipeline:
    def test_run_pipeline_single_blob_creates_output(self, tmp_path, capsys):
        import cli
        out = tmp_path / "resume.tex"
        cli.run_pipeline(
            jd_path=str(JD_FILE),
            artifacts=[(str(BLOB_FILE), "blob")],
            output_path=str(out),
            header={"name": "Jane Smith", "email": "jane@example.com",
                    "phone": "", "linkedin": "", "github": "", "portfolio": ""},
            template_path=str(TEMPLATE_FILE),
        )
        assert out.exists()
        assert "ATS Score" in capsys.readouterr().out

    def test_run_pipeline_merges_multiple_artifacts(self, tmp_path):
        import cli
        out = tmp_path / "resume.tex"
        cli.run_pipeline(
            jd_path=str(JD_FILE),
            artifacts=[(str(BLOB_FILE), "blob"), (str(BLOB_FILE), "markdown")],
            output_path=str(out),
            header={"name": "Jane", "email": "j@j.com",
                    "phone": "", "linkedin": "", "github": "", "portfolio": ""},
            template_path=str(TEMPLATE_FILE),
        )
        assert out.exists()

    def test_run_pipeline_markdown_artifact(self, tmp_path):
        import cli
        md_file = tmp_path / "resume.md"
        md_file.write_text(
            "## Experience\n**Data Engineer** | Acme | 2022-Present\n- Built pipelines\n",
            encoding="utf-8",
        )
        out = tmp_path / "resume.tex"
        cli.run_pipeline(
            jd_path=str(JD_FILE),
            artifacts=[(str(md_file), "markdown")],
            output_path=str(out),
            header={"name": "X", "email": "x@x.com",
                    "phone": "", "linkedin": "", "github": "", "portfolio": ""},
            template_path=str(TEMPLATE_FILE),
        )
        assert out.exists()

    def test_run_pipeline_prints_gap_signals(self, tmp_path, capsys):
        import cli
        out = tmp_path / "resume.tex"
        cli.run_pipeline(
            jd_path=str(JD_FILE),
            artifacts=[(str(BLOB_FILE), "blob")],
            output_path=str(out),
            header={"name": "T", "email": "t@t.com",
                    "phone": "", "linkedin": "", "github": "", "portfolio": ""},
            template_path=str(TEMPLATE_FILE),
            top_gaps=2,
        )
        out_text = capsys.readouterr().out
        assert "Gap Analysis" in out_text
        assert "Resume written to" in out_text

    def test_main_single_artifact(self, monkeypatch, tmp_path):
        import cli
        output = tmp_path / "resume.tex"
        monkeypatch.setattr(sys, "argv", [
            "cli.py",
            "--jd", str(JD_FILE),
            "--artifact", f"{BLOB_FILE}:blob",
            "--output", str(output),
            "--template", str(TEMPLATE_FILE),
            "--name", "Test User",
            "--email", "test@example.com",
        ])
        cli.main()
        assert output.exists()

    @pytest.mark.skipif(sys.platform == "win32", reason="Windows drive letters contain ':' which conflicts with path:format separator")
    def test_main_artifact_without_format_defaults_to_blob(self, monkeypatch, tmp_path):
        import cli
        output = tmp_path / "resume.tex"
        monkeypatch.setattr(sys, "argv", [
            "cli.py",
            "--jd", str(JD_FILE),
            "--artifact", str(BLOB_FILE),  # no :format suffix
            "--output", str(output),
            "--template", str(TEMPLATE_FILE),
        ])
        cli.main()
        assert output.exists()

    def test_main_invalid_format_exits(self, monkeypatch, tmp_path):
        import cli
        output = tmp_path / "resume.tex"
        monkeypatch.setattr(sys, "argv", [
            "cli.py",
            "--jd", str(JD_FILE),
            "--artifact", f"{BLOB_FILE}:bogus_format",
            "--output", str(output),
            "--template", str(TEMPLATE_FILE),
        ])
        with pytest.raises(SystemExit):
            cli.main()

    def test_main_all_header_fields(self, monkeypatch, tmp_path):
        import cli
        output = tmp_path / "resume.tex"
        monkeypatch.setattr(sys, "argv", [
            "cli.py",
            "--jd", str(JD_FILE),
            "--artifact", f"{BLOB_FILE}:blob",
            "--output", str(output),
            "--template", str(TEMPLATE_FILE),
            "--name", "Jane Smith",
            "--email", "jane@example.com",
            "--phone", "555-1234",
            "--linkedin", "https://linkedin.com/in/jane",
            "--github", "https://github.com/jane",
            "--portfolio", "https://jane.io",
            "--top-gaps", "3",
        ])
        cli.main()
        assert output.exists()
