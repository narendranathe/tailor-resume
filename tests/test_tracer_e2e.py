"""
Tracer bullet: end-to-end pipeline test.
parse_blob -> run_analysis -> build_from_profile -> out/resume.tex

Tests are written RED first — fixtures and requirements.txt do not exist yet.
"""
import json
import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).parent.parent / ".claude" / "skills" / "tailor-resume" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# Test 1: fixtures exist and are non-empty
# ---------------------------------------------------------------------------
class TestFixturesExist:
    def test_sample_jd_is_readable(self, sample_jd_text):
        assert len(sample_jd_text) > 100, "JD fixture must be a realistic job description"

    def test_sample_blob_is_readable(self, sample_blob_text):
        assert len(sample_blob_text) > 100, "Blob fixture must contain work experience"

    def test_sample_profile_is_valid_json(self, sample_profile_dict):
        assert isinstance(sample_profile_dict, dict)
        assert "experience" in sample_profile_dict

    def test_fixtures_contain_no_pii(self, sample_jd_text, sample_blob_text):
        """No real names, phone numbers, or personal emails in fixtures."""
        pii_markers = [
            "narendranathe", "edara", "573-466", "edara.narendranath",
            "ExponentHR", "Missouri S&T",
        ]
        combined = sample_jd_text + sample_blob_text
        for marker in pii_markers:
            assert marker not in combined, f"PII found in fixture: {marker!r}"


# ---------------------------------------------------------------------------
# Test 2: profile_extractor parses the blob fixture
# ---------------------------------------------------------------------------
class TestProfileExtractor:
    def test_parse_blob_returns_profile_with_experience(self, sample_blob_text):
        from profile_extractor import parse_blob, profile_to_dict
        profile = parse_blob(sample_blob_text)
        d = profile_to_dict(profile)
        assert len(d["experience"]) >= 2, "Blob should contain at least 2 roles"

    def test_parse_blob_roles_have_titles(self, sample_blob_text):
        from profile_extractor import parse_blob, profile_to_dict
        profile = parse_blob(sample_blob_text)
        d = profile_to_dict(profile)
        for role in d["experience"]:
            assert role["title"], f"Role missing title: {role}"

    def test_parse_blob_bullets_have_text(self, sample_blob_text):
        from profile_extractor import parse_blob, profile_to_dict
        profile = parse_blob(sample_blob_text)
        d = profile_to_dict(profile)
        all_bullets = [b for r in d["experience"] for b in r["bullets"]]
        assert len(all_bullets) >= 3, "Should extract at least 3 bullets from blob"

    def test_parse_blob_detects_metrics(self, sample_blob_text):
        from profile_extractor import parse_blob, profile_to_dict
        profile = parse_blob(sample_blob_text)
        d = profile_to_dict(profile)
        bullets_with_metrics = [
            b for r in d["experience"]
            for b in r["bullets"]
            if b["metrics"]
        ]
        assert len(bullets_with_metrics) >= 1, "At least one bullet should have metrics"

    def test_profile_to_dict_is_json_serializable(self, sample_blob_text):
        from profile_extractor import parse_blob, profile_to_dict
        profile = parse_blob(sample_blob_text)
        d = profile_to_dict(profile)
        # Must round-trip through JSON without error
        serialized = json.dumps(d)
        restored = json.loads(serialized)
        assert restored["experience"] == d["experience"]


# ---------------------------------------------------------------------------
# Test 3: jd_gap_analyzer runs against the parsed profile
# ---------------------------------------------------------------------------
class TestJdGapAnalyzer:
    def test_run_analysis_returns_report(self, sample_jd_text, sample_blob_text):
        from jd_gap_analyzer import run_analysis
        from profile_extractor import parse_blob, profile_to_dict
        profile = parse_blob(sample_blob_text)
        resume_text = json.dumps(profile_to_dict(profile))
        report = run_analysis(sample_jd_text, resume_text)
        assert hasattr(report, "ats_score_estimate")
        assert hasattr(report, "top_missing")

    def test_ats_score_is_in_valid_range(self, sample_jd_text, sample_blob_text):
        from jd_gap_analyzer import run_analysis
        from profile_extractor import parse_blob, profile_to_dict
        profile = parse_blob(sample_blob_text)
        resume_text = json.dumps(profile_to_dict(profile))
        report = run_analysis(sample_jd_text, resume_text)
        assert 0 <= report.ats_score_estimate <= 100

    def test_gap_analysis_surfaces_missing_signals(self, sample_jd_text, sample_blob_text):
        """JD has Airflow/data quality/CI-CD; blob should not cover all of them."""
        from jd_gap_analyzer import run_analysis
        from profile_extractor import parse_blob, profile_to_dict
        profile = parse_blob(sample_blob_text)
        resume_text = json.dumps(profile_to_dict(profile))
        report = run_analysis(sample_jd_text, resume_text)
        assert len(report.top_missing) >= 1, "JD should surface at least 1 gap"

    def test_gap_signals_have_suggested_angles(self, sample_jd_text, sample_blob_text):
        from jd_gap_analyzer import run_analysis
        from profile_extractor import parse_blob, profile_to_dict
        profile = parse_blob(sample_blob_text)
        resume_text = json.dumps(profile_to_dict(profile))
        report = run_analysis(sample_jd_text, resume_text)
        for signal in report.top_missing:
            assert signal.suggested_angles, f"Gap {signal.category!r} has no suggested angles"


# ---------------------------------------------------------------------------
# Test 4: latex_renderer produces valid .tex from profile
# ---------------------------------------------------------------------------
class TestLatexRenderer:
    def test_build_from_profile_creates_file(self, sample_profile_dict, template_path, out_dir):
        from latex_renderer import build_from_profile
        output_path = str(out_dir / "resume.tex")
        header = {
            "name": "Jane Smith",
            "phone": "",
            "email": "jane@example.com",
            "linkedin": "https://linkedin.com/in/jane-smith",
            "github": "",
            "portfolio": "https://janesmith.dev",
        }
        build_from_profile(sample_profile_dict, template_path, output_path, header)
        assert Path(output_path).exists(), "resume.tex was not created"

    def test_output_contains_resume_structure(self, sample_profile_dict, template_path, out_dir):
        from latex_renderer import build_from_profile
        output_path = str(out_dir / "resume.tex")
        header = {"name": "Jane Smith", "phone": "", "email": "jane@example.com",
                  "linkedin": "", "github": "", "portfolio": ""}
        build_from_profile(sample_profile_dict, template_path, output_path, header)
        content = Path(output_path).read_text(encoding="utf-8")
        assert r"\resumeItem" in content, "Output missing \\resumeItem commands"
        assert r"\section" in content, "Output missing \\section commands"

    def test_output_contains_injected_name(self, sample_profile_dict, template_path, out_dir):
        from latex_renderer import build_from_profile
        output_path = str(out_dir / "resume.tex")
        header = {"name": "Jane Smith", "phone": "", "email": "jane@example.com",
                  "linkedin": "", "github": "", "portfolio": ""}
        build_from_profile(sample_profile_dict, template_path, output_path, header)
        content = Path(output_path).read_text(encoding="utf-8")
        assert "Jane Smith" in content

    def test_no_unfilled_placeholders(self, sample_profile_dict, template_path, out_dir):
        """After rendering, no {{KEY}} tokens should remain in output."""
        from latex_renderer import build_from_profile
        import re
        output_path = str(out_dir / "resume.tex")
        header = {"name": "Jane Smith", "phone": "555-0100", "email": "jane@example.com",
                  "linkedin": "https://linkedin.com/in/jane", "github": "", "portfolio": "https://jane.dev"}
        build_from_profile(sample_profile_dict, template_path, output_path, header)
        content = Path(output_path).read_text(encoding="utf-8")
        remaining = re.findall(r"\{\{[A-Z_]+\}\}", content)
        assert not remaining, f"Unfilled placeholders remain: {remaining}"


# ---------------------------------------------------------------------------
# Test 5: full end-to-end pipeline chain
# ---------------------------------------------------------------------------
class TestEndToEndPipeline:
    def test_full_pipeline_blob_to_tex(self, sample_jd_text, sample_blob_text,
                                       template_path, out_dir):
        """
        Tracer bullet: parse_blob -> run_analysis -> build_from_profile -> resume.tex
        This is the single most important test — proves the whole pipeline works.
        """
        from profile_extractor import parse_blob, profile_to_dict
        from jd_gap_analyzer import run_analysis
        from latex_renderer import build_from_profile

        # Step 1: parse
        profile = parse_blob(sample_blob_text)
        profile_dict = profile_to_dict(profile)

        # Step 2: analyze
        resume_text = json.dumps(profile_dict)
        report = run_analysis(sample_jd_text, resume_text)
        assert 0 <= report.ats_score_estimate <= 100

        # Step 3: render
        output_path = str(out_dir / "resume.tex")
        header = {"name": "Jane Smith", "phone": "", "email": "jane@example.com",
                  "linkedin": "", "github": "", "portfolio": ""}
        build_from_profile(profile_dict, template_path, output_path, header)

        # Step 4: verify output
        content = Path(output_path).read_text(encoding="utf-8")
        assert Path(output_path).exists()
        assert r"\begin{document}" in content
        assert r"\resumeItem" in content
        assert "Jane Smith" in content

    def test_pipeline_output_is_single_document(self, sample_blob_text, template_path, out_dir):
        """Output must be a single \begin{document}...\end{document} block."""
        from profile_extractor import parse_blob, profile_to_dict
        from latex_renderer import build_from_profile

        profile_dict = profile_to_dict(parse_blob(sample_blob_text))
        output_path = str(out_dir / "resume.tex")
        header = {"name": "Test User", "phone": "", "email": "test@example.com",
                  "linkedin": "", "github": "", "portfolio": ""}
        build_from_profile(profile_dict, template_path, output_path, header)
        content = Path(output_path).read_text(encoding="utf-8")

        assert content.count(r"\begin{document}") == 1
        assert content.count(r"\end{document}") == 1
