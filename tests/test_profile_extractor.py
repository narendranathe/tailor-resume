"""Tests for profile_extractor.py — all parsers, helpers, and new PDF/DOCX/auto-detect."""
import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude/skills/tailor-resume/scripts"))

from profile_extractor import (
    parse_blob,
    parse_markdown,
    parse_latex,
    parse_linkedin,
    parse_pdf,
    parse_docx,
    merge_profiles,
    auto_detect_format,
    _extract_args,
    _clean_latex,
    _split_sections_latex,
    _parse_dates,
    _dedupe,
    _detect_section,
    _parse_plain_resume_text,
    profile_to_dict,
    extract_metrics,
    extract_tools,
    score_confidence,
    Role,
    Profile,
)


# ---------------------------------------------------------------------------
# extract_metrics
# ---------------------------------------------------------------------------
class TestExtractMetrics:
    def test_detects_percentage(self):
        metrics = extract_metrics("Reduced latency by 45%")
        assert len(metrics) >= 1

    def test_detects_dollar_amount(self):
        metrics = extract_metrics("Saved $4,100/month in compute costs")
        assert len(metrics) >= 1

    def test_detects_time_range(self):
        metrics = extract_metrics("Cut runtime from 45 min to 9 min")
        assert len(metrics) >= 1

    def test_empty_string_returns_empty(self):
        assert extract_metrics("") == []

    def test_plain_text_no_metrics(self):
        assert extract_metrics("Led cross-functional team meetings") == []


# ---------------------------------------------------------------------------
# extract_tools
# ---------------------------------------------------------------------------
class TestExtractTools:
    def test_detects_airflow(self):
        tools = extract_tools("Built Airflow DAGs with backfill strategy")
        assert "airflow" in [t.lower() for t in tools]

    def test_detects_spark(self):
        tools = extract_tools("Optimized Spark jobs for 10x speedup")
        assert "spark" in [t.lower() for t in tools]

    def test_detects_python(self):
        tools = extract_tools("Wrote Python ETL pipeline")
        assert "python" in [t.lower() for t in tools]

    def test_detects_multiple_tools(self):
        tools = extract_tools("Used Airflow, Spark, and Delta Lake")
        lower = [t.lower() for t in tools]
        assert "airflow" in lower or "spark" in lower


# ---------------------------------------------------------------------------
# score_confidence
# ---------------------------------------------------------------------------
class TestScoreConfidence:
    def test_quantified_bullet_scores_high_or_medium(self):
        score = score_confidence("Reduced costs by 68% saving $4,100/month via ETL refactor")
        assert score in ("high", "medium")

    def test_vague_bullet_scores_low(self):
        score = score_confidence("Worked on data pipelines")
        assert score == "low"

    def test_single_metric_scores_medium(self):
        score = score_confidence("Cut pipeline runtime by 50%")
        assert score in ("medium", "high")

    def test_score_returns_string(self):
        s = score_confidence("Built something")
        assert isinstance(s, str)
        assert s in ("high", "medium", "low")


# ---------------------------------------------------------------------------
# _extract_args (brace-counting helper)
# ---------------------------------------------------------------------------
class TestExtractArgs:
    def test_single_arg(self):
        args, pos = _extract_args("{hello}", 0, 1)
        assert args == ["hello"]
        assert pos == 7

    def test_multiple_args(self):
        args, pos = _extract_args("{foo}{bar}{baz}", 0, 3)
        assert args == ["foo", "bar", "baz"]

    def test_args_with_whitespace_between(self):
        args, pos = _extract_args("{a}  \n  {b}", 0, 2)
        assert args == ["a", "b"]

    def test_nested_braces(self):
        args, pos = _extract_args("{\\href{url}{label}}", 0, 1)
        assert "\\href" in args[0]

    def test_request_more_args_than_available(self):
        args, _ = _extract_args("{only one}", 0, 3)
        assert len(args) == 1

    def test_empty_string(self):
        args, _ = _extract_args("", 0, 2)
        assert args == []

    def test_partial_start_position(self):
        text = "prefix{value}"
        args, _ = _extract_args(text, 6, 1)
        assert args == ["value"]


# ---------------------------------------------------------------------------
# _clean_latex
# ---------------------------------------------------------------------------
class TestCleanLatex:
    def test_removes_textbf(self):
        result = _clean_latex("\\textbf{Bold Text}")
        assert "Bold Text" in result
        assert "\\textbf" not in result

    def test_removes_textit(self):
        result = _clean_latex("\\textit{Italic}")
        assert "Italic" in result
        assert "\\textit" not in result

    def test_unwraps_href(self):
        result = _clean_latex("\\href{https://example.com}{Click here}")
        assert "Click here" in result
        assert "https://example.com" not in result

    def test_replaces_double_dash(self):
        result = _clean_latex("Jan 2020 -- Present")
        assert "--" not in result or "–" in result or "Jan" in result

    def test_removes_latex_percent_escape(self):
        result = _clean_latex("Reduced by 40\\%")
        assert "40%" in result

    def test_normalizes_whitespace(self):
        result = _clean_latex("a   b   c")
        assert "  " not in result

    def test_empty_string(self):
        assert _clean_latex("") == ""


# ---------------------------------------------------------------------------
# _split_sections_latex
# ---------------------------------------------------------------------------
class TestSplitSectionsLatex:
    def test_splits_two_sections(self):
        tex = "\\section{Experience}\nsome content\n\\section{Skills}\nskill content"
        sections = _split_sections_latex(tex)
        assert "experience" in sections
        assert "skills" in sections

    def test_section_content_correct(self):
        tex = "\\section{Education}\nedu stuff\n\\section{Projects}\nproj stuff"
        sections = _split_sections_latex(tex)
        assert "edu" in sections["education"]
        assert "proj" in sections["projects"]

    def test_empty_text_returns_empty_dict(self):
        assert _split_sections_latex("no sections here") == {}

    def test_single_section(self):
        sections = _split_sections_latex("\\section{Experience}\ncontent")
        assert "experience" in sections


# ---------------------------------------------------------------------------
# _parse_dates
# ---------------------------------------------------------------------------
class TestParseDates:
    def test_en_dash(self):
        start, end = _parse_dates("Jan 2022 – Present")
        assert "Jan 2022" in start
        assert "Present" in end

    def test_double_dash(self):
        start, end = _parse_dates("July 2024 -- Present")
        assert start.strip() != ""
        assert end.strip() != ""

    def test_no_separator_returns_full_as_start(self):
        start, end = _parse_dates("2022")
        assert start == "2022"
        assert end == ""

    def test_year_range(self):
        start, end = _parse_dates("2020 - 2022")
        assert "2020" in start
        assert "2022" in end


# ---------------------------------------------------------------------------
# _dedupe
# ---------------------------------------------------------------------------
class TestDedupe:
    def test_removes_duplicates(self):
        assert _dedupe(["a", "b", "a", "c"]) == ["a", "b", "c"]

    def test_preserves_order(self):
        assert _dedupe(["z", "a", "m"]) == ["z", "a", "m"]

    def test_empty_list(self):
        assert _dedupe([]) == []

    def test_no_duplicates_unchanged(self):
        lst = ["x", "y", "z"]
        assert _dedupe(lst) == lst


# ---------------------------------------------------------------------------
# _detect_section
# ---------------------------------------------------------------------------
class TestDetectSection:
    def test_detects_experience(self):
        assert _detect_section("Experience") == "experience"

    def test_detects_education(self):
        assert _detect_section("Education") == "education"

    def test_detects_skills(self):
        assert _detect_section("Technical Skills") == "skills"

    def test_detects_projects(self):
        assert _detect_section("Projects") == "projects"

    def test_detects_certifications(self):
        assert _detect_section("Certifications") == "certifications"

    def test_case_insensitive(self):
        assert _detect_section("EXPERIENCE") == "experience"

    def test_with_trailing_colon(self):
        assert _detect_section("Skills:") == "skills"

    def test_unknown_returns_none(self):
        assert _detect_section("Random Section Header") is None

    def test_empty_string_returns_none(self):
        assert _detect_section("") is None

    def test_detects_work_experience(self):
        assert _detect_section("Work Experience") == "experience"


# ---------------------------------------------------------------------------
# parse_markdown
# ---------------------------------------------------------------------------
class TestParseMarkdown:
    SAMPLE_MD = """\
## Experience

**Senior Data Engineer** | DataWorks Inc | Jan 2022 - Present
- Built governed semantic layer on Databricks, cutting metric discrepancies from 12/week to zero
- Owned CI/CD via Azure DevOps, compressing deployments from 8 weeks to 6 days

**Data Engineer** | Acme Analytics | Jun 2020 - Dec 2021
- Designed partitioned Delta Lake tables, cutting query time by 60%

## Skills

Python, SQL, Spark, Airflow, Delta Lake
"""

    def test_parse_markdown_returns_profile(self):
        profile = parse_markdown(self.SAMPLE_MD)
        assert isinstance(profile, Profile)

    def test_parse_markdown_extracts_roles(self):
        profile = parse_markdown(self.SAMPLE_MD)
        assert len(profile.experience) >= 1

    def test_parse_markdown_extracts_bullets(self):
        profile = parse_markdown(self.SAMPLE_MD)
        total_bullets = sum(len(r.bullets) for r in profile.experience)
        assert total_bullets >= 1

    def test_parse_markdown_extracts_skills(self):
        profile = parse_markdown(self.SAMPLE_MD)
        assert len(profile.skills) >= 1

    def test_parse_markdown_role_has_title(self):
        profile = parse_markdown(self.SAMPLE_MD)
        titles = [r.title for r in profile.experience]
        assert any("Data Engineer" in t for t in titles)

    def test_parse_markdown_empty_text(self):
        profile = parse_markdown("")
        assert profile.experience == []


# ---------------------------------------------------------------------------
# parse_latex — single-line (backward-compat)
# ---------------------------------------------------------------------------
class TestParseLatex:
    SAMPLE_LATEX = (
        r"\section{Experience}" + "\n"
        r"  \resumeSubHeadingListStart" + "\n"
        r"    \resumeSubheading{Senior Data Engineer}{Jan 2022 -- Present}{DataWorks Inc}{Remote}" + "\n"
        r"      \resumeItemListStart" + "\n"
        r"        \resumeItem{Built governed semantic layer on Databricks}" + "\n"
        r"        \resumeItem{Owned CI/CD via Azure DevOps}" + "\n"
        r"      \resumeItemListEnd" + "\n"
        r"  \resumeSubHeadingListEnd" + "\n"
        "\n"
        r"\section{Projects}" + "\n"
        r"    \resumeSubHeadingListStart" + "\n"
        r"      \resumeProjectHeading{\textbf{Analytics Dashboard} $|$ \emph{Python, Streamlit}}{2023}" + "\n"
        r"          \resumeItemListStart" + "\n"
        r"            \resumeItem{Built real-time analytics dashboard serving 1k users}" + "\n"
        r"          \resumeItemListEnd" + "\n"
        r"    \resumeSubHeadingListEnd" + "\n"
    )

    def test_parse_latex_returns_profile(self):
        profile = parse_latex(self.SAMPLE_LATEX)
        assert isinstance(profile, Profile)

    def test_parse_latex_extracts_experience(self):
        profile = parse_latex(self.SAMPLE_LATEX)
        assert len(profile.experience) >= 1

    def test_parse_latex_extracts_bullets(self):
        profile = parse_latex(self.SAMPLE_LATEX)
        total = sum(len(r.bullets) for r in profile.experience)
        assert total >= 1

    def test_parse_latex_extracts_projects(self):
        profile = parse_latex(self.SAMPLE_LATEX)
        assert len(profile.projects) >= 1

    def test_parse_latex_project_has_bullets(self):
        profile = parse_latex(self.SAMPLE_LATEX)
        project_bullets = sum(len(p.bullets) for p in profile.projects)
        assert project_bullets >= 1

    def test_parse_latex_role_title(self):
        profile = parse_latex(self.SAMPLE_LATEX)
        assert profile.experience[0].title == "Senior Data Engineer"

    def test_parse_latex_empty_text(self):
        profile = parse_latex("")
        assert profile.experience == []


# ---------------------------------------------------------------------------
# parse_latex — multiline (Jake template style)
# ---------------------------------------------------------------------------
class TestParseLatexMultiline:
    """The real resume uses \resumeSubheading over 3 lines — this is the primary use case."""

    MULTILINE_LATEX = (
        r"\section{Experience}" + "\n"
        r"  \resumeSubHeadingListStart" + "\n"
        r"    \resumeSubheading" + "\n"
        r"      {Data Engineer}{July 2024 -- Present}" + "\n"
        r"      {ExponentHR Technologies}{Dallas, TX}" + "\n"
        r"      \resumeItemListStart" + "\n"
        r"        \resumeItem{Architected AI-powered analytics platform, reducing support volume by 40\%}" + "\n"
        r"        \resumeItem{Compressed deployment cycles from 3 months to 14 days (85\% faster)}" + "\n"
        r"      \resumeItemListEnd" + "\n"
        r"    \resumeSubheading" + "\n"
        r"      {Data Engineer -- Research}{Aug. 2023 -- July 2024}" + "\n"
        r"      {Missouri S\&T}{Rolla, MO}" + "\n"
        r"      \resumeItemListStart" + "\n"
        r"        \resumeItem{Managed university webpages and data infrastructure}" + "\n"
        r"      \resumeItemListEnd" + "\n"
        r"  \resumeSubHeadingListEnd" + "\n"
        "\n"
        r"\section{Education}" + "\n"
        r"  \resumeSubHeadingListStart" + "\n"
        r"    \resumeSubheading" + "\n"
        r"      {Missouri University of Science and Technology}{Rolla, MO}" + "\n"
        r"      {Master of Science in Information Science}{Jan. 2022 -- Dec. 2023}" + "\n"
        r"  \resumeSubHeadingListEnd" + "\n"
        "\n"
        r"\section{Technical Skills}" + "\n"
        r" \begin{itemize}" + "\n"
        r"    \small{\item{" + "\n"
        r"     \textbf{Languages \& ML}{: Python, SQL, Bash, MLflow, Airflow} \\" + "\n"
        r"     \textbf{Data \& Cloud}{: Spark, Kafka, Databricks, Azure} \\" + "\n"
        r"    }}" + "\n"
        r" \end{itemize}" + "\n"
        "\n"
        r"\section{Certifications \& Publications}" + "\n"
        r" \begin{itemize}" + "\n"
        r"    \small{\item{" + "\n"
        r"     \textbf{DP-700}{: Microsoft Certified Data Engineer Associate}" + "\n"
        r"    }}" + "\n"
        r" \end{itemize}" + "\n"
    )

    def test_multiline_subheading_extracts_roles(self):
        profile = parse_latex(self.MULTILINE_LATEX)
        assert len(profile.experience) == 2

    def test_multiline_first_role_title(self):
        profile = parse_latex(self.MULTILINE_LATEX)
        assert "Data Engineer" in profile.experience[0].title

    def test_multiline_first_role_company(self):
        profile = parse_latex(self.MULTILINE_LATEX)
        assert "ExponentHR" in profile.experience[0].company

    def test_multiline_role_has_bullets(self):
        profile = parse_latex(self.MULTILINE_LATEX)
        assert len(profile.experience[0].bullets) >= 1

    def test_multiline_bullet_text_clean(self):
        profile = parse_latex(self.MULTILINE_LATEX)
        bullet_text = profile.experience[0].bullets[0].text
        assert "40%" in bullet_text
        assert "\\" not in bullet_text

    def test_multiline_education_parsed(self):
        profile = parse_latex(self.MULTILINE_LATEX)
        assert len(profile.education) >= 1
        assert any("Missouri" in e.get("institution", "") for e in profile.education)

    def test_multiline_skills_parsed(self):
        profile = parse_latex(self.MULTILINE_LATEX)
        assert len(profile.skills) >= 3
        skill_names = [s.lower() for s in profile.skills]
        assert any("python" in s for s in skill_names)

    def test_multiline_certifications_parsed(self):
        profile = parse_latex(self.MULTILINE_LATEX)
        assert len(profile.certifications) >= 1

    def test_multiline_dates_parsed(self):
        profile = parse_latex(self.MULTILINE_LATEX)
        role = profile.experience[0]
        assert role.start != "" or role.end != ""

    def test_second_role_correct(self):
        profile = parse_latex(self.MULTILINE_LATEX)
        second = profile.experience[1]
        assert "Missouri" in second.company or "Rolla" in second.location


# ---------------------------------------------------------------------------
# auto_detect_format
# ---------------------------------------------------------------------------
class TestAutoDetectFormat:
    def test_detects_latex_from_documentclass(self):
        tex = r"\documentclass[letterpaper]{article}\n\begin{document}\end{document}"
        assert auto_detect_format(tex) == "latex"

    def test_detects_latex_from_resumeitem(self):
        tex = r"\resumeItem{Built something}\resumeSubheading{DE}{2022}{Acme}{TX}"
        assert auto_detect_format(tex) == "latex"

    def test_detects_markdown(self):
        md = "## Experience\n**Engineer** | Acme | 2022\n- Built thing"
        assert auto_detect_format(md) == "markdown"

    def test_defaults_to_blob(self):
        plain = "Senior Data Engineer at Acme Corp from 2020 to 2022"
        assert auto_detect_format(plain) == "blob"

    def test_single_hash_heading_is_markdown(self):
        md = "# Resume\n## Skills\nPython, SQL"
        assert auto_detect_format(md) == "markdown"


# ---------------------------------------------------------------------------
# _parse_plain_resume_text (PDF/DOCX extracted text)
# ---------------------------------------------------------------------------
class TestParsePlainResumeText:
    PLAIN_TEXT = """\
Experience
Data Engineer  ExponentHR Technologies  July 2024 – Present
• Architected AI-powered analytics platform reducing support by 40%
• Compressed deployment cycles from 3 months to 14 days

Data Engineer  Missouri S&T  Aug 2023 – July 2024
• Managed university infrastructure and data pipelines

Education
Missouri University of Science and Technology
Master of Science in Information Science 2022 – 2023

Skills
Python, SQL, Spark, Kafka, Airflow, Docker, Azure

Certifications
DP-700 Microsoft Certified Data Engineer Associate
"""

    def test_returns_profile(self):
        p = _parse_plain_resume_text(self.PLAIN_TEXT)
        assert isinstance(p, Profile)

    def test_extracts_experience_roles(self):
        p = _parse_plain_resume_text(self.PLAIN_TEXT)
        assert len(p.experience) >= 1

    def test_extracts_bullets(self):
        p = _parse_plain_resume_text(self.PLAIN_TEXT)
        total = sum(len(r.bullets) for r in p.experience)
        assert total >= 1

    def test_extracts_skills(self):
        p = _parse_plain_resume_text(self.PLAIN_TEXT)
        assert len(p.skills) >= 3

    def test_extracts_certifications(self):
        p = _parse_plain_resume_text(self.PLAIN_TEXT)
        assert len(p.certifications) >= 1

    def test_skills_contain_python(self):
        p = _parse_plain_resume_text(self.PLAIN_TEXT)
        skill_names = [s.lower() for s in p.skills]
        assert any("python" in s for s in skill_names)

    def test_empty_text_returns_empty_profile(self):
        p = _parse_plain_resume_text("")
        assert isinstance(p, Profile)

    def test_skills_deduped(self):
        text = "Skills\nPython, Python, SQL\nExperience"
        p = _parse_plain_resume_text(text)
        assert p.skills.count("Python") <= 1

    def test_bullet_with_dash_prefix(self):
        text = "Experience\nData Engineer  Acme Corp  2022 – 2024\n- Built a pipeline saving 30% cost"
        p = _parse_plain_resume_text(text)
        bullets = sum(len(r.bullets) for r in p.experience)
        assert bullets >= 1


# ---------------------------------------------------------------------------
# parse_pdf
# ---------------------------------------------------------------------------
class TestParsePdf:
    def test_parse_pdf_returns_profile_with_pypdf(self):
        pytest.importorskip("pypdf", reason="pypdf not installed")
        from pypdf import PdfWriter
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        buf = io.BytesIO()
        writer.write(buf)
        pdf_bytes = buf.getvalue()
        profile = parse_pdf(pdf_bytes)
        assert isinstance(profile, Profile)

    def test_parse_pdf_raises_import_error_without_pypdf(self, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "pypdf":
                raise ImportError("No module named 'pypdf'")
            return real_import(name, *args, **kwargs)

        # Remove cached module to force re-import
        saved = sys.modules.pop("pypdf", None)
        monkeypatch.setattr(builtins, "__import__", mock_import)
        try:
            with pytest.raises(ImportError, match="pypdf"):
                parse_pdf(b"fake pdf bytes")
        finally:
            monkeypatch.setattr(builtins, "__import__", real_import)
            if saved is not None:
                sys.modules["pypdf"] = saved


# ---------------------------------------------------------------------------
# parse_docx
# ---------------------------------------------------------------------------
class TestParseDocx:
    def test_parse_docx_returns_profile_with_python_docx(self):
        pytest.importorskip("docx", reason="python-docx not installed")
        from docx import Document
        doc = Document()
        doc.add_paragraph("Experience")
        doc.add_paragraph("Data Engineer  Acme Corp  2022 – 2024")
        doc.add_paragraph("• Built a streaming pipeline processing 1M events/day")
        doc.add_paragraph("Skills")
        doc.add_paragraph("Python, SQL, Spark")
        buf = io.BytesIO()
        doc.save(buf)
        docx_bytes = buf.getvalue()
        profile = parse_docx(docx_bytes)
        assert isinstance(profile, Profile)

    def test_parse_docx_raises_import_error_without_docx(self, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "docx":
                raise ImportError("No module named 'docx'")
            return real_import(name, *args, **kwargs)

        saved = sys.modules.pop("docx", None)
        monkeypatch.setattr(builtins, "__import__", mock_import)
        try:
            with pytest.raises(ImportError, match="python-docx"):
                parse_docx(b"fake docx bytes")
        finally:
            monkeypatch.setattr(builtins, "__import__", real_import)
            if saved is not None:
                sys.modules["docx"] = saved


# ---------------------------------------------------------------------------
# parse_linkedin
# ---------------------------------------------------------------------------
class TestParseLinkedin:
    def test_parse_linkedin_returns_profile(self):
        text = "Senior Data Engineer at DataWorks Inc\n- Built pipelines\n- Reduced costs by 40%"
        profile = parse_linkedin(text)
        assert isinstance(profile, Profile)


# ---------------------------------------------------------------------------
# merge_profiles
# ---------------------------------------------------------------------------
class TestMergeProfiles:
    def test_merge_combines_experience(self):
        p1 = Profile()
        p1.experience.append(Role(title="DE", company="A", start="2020", end="2021", location=""))
        p2 = Profile()
        p2.experience.append(Role(title="SDE", company="B", start="2021", end="2022", location=""))
        merged = merge_profiles(p1, p2)
        assert len(merged.experience) == 2

    def test_merge_dedupes_skills(self):
        p1 = Profile()
        p1.skills = ["Python", "SQL"]
        p2 = Profile()
        p2.skills = ["Python", "Airflow"]
        merged = merge_profiles(p1, p2)
        assert merged.skills.count("Python") == 1

    def test_merge_empty_profiles(self):
        merged = merge_profiles(Profile(), Profile())
        assert merged.experience == []
        assert merged.skills == []

    def test_merge_three_profiles(self):
        p1, p2, p3 = Profile(), Profile(), Profile()
        p1.skills = ["Python"]
        p2.skills = ["SQL"]
        p3.skills = ["Spark"]
        merged = merge_profiles(p1, p2, p3)
        assert len(merged.skills) == 3


# ---------------------------------------------------------------------------
# profile_to_dict
# ---------------------------------------------------------------------------
class TestProfileToDict:
    def test_profile_to_dict_is_serializable(self):
        profile = parse_blob(
            "Company: DataWorks\nTitle: DE\n- Built pipeline saving $1k/month"
        )
        d = profile_to_dict(profile)
        json.dumps(d)

    def test_profile_to_dict_has_experience_key(self):
        profile = Profile()
        d = profile_to_dict(profile)
        assert "experience" in d
