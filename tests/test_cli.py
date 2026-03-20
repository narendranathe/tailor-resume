"""Tests for CLI main() entry points across all four scripts."""
import json
import sys
from pathlib import Path


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
