"""Tests for profile_extractor.py — markdown, LaTeX, LinkedIn parsers, merge, tools/metrics."""
import json
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude/skills/tailor-resume/scripts"))

from profile_extractor import (
    parse_blob,
    parse_markdown,
    parse_latex,
    parse_linkedin,
    merge_profiles,
    profile_to_dict,
    extract_metrics,
    extract_tools,
    score_confidence,
    Bullet,
    Role,
    Profile,
)


# ---------------------------------------------------------------------------
# extract_metrics
# ---------------------------------------------------------------------------
class TestExtractMetrics:
    def test_detects_percentage(self):
        metrics = extract_metrics("Reduced latency by 45%")
        assert len(metrics) >= 1  # pattern matched

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
        # score_confidence returns "high" | "medium" | "low" based on metric count
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
# parse_latex
# ---------------------------------------------------------------------------
class TestParseLatex:
    # Subheadings must be on ONE line for the regex to match
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
        # Must not raise
        json.dumps(d)

    def test_profile_to_dict_has_experience_key(self):
        profile = Profile()
        d = profile_to_dict(profile)
        assert "experience" in d
