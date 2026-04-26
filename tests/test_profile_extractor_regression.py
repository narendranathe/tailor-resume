"""
test_profile_extractor_regression.py

Characterization tests for profile_extractor.py.

These tests pin the CURRENT behavior of the parser so that when
profile_extractor.py is split into a parsers/ package (GitHub issue #51),
any accidental behavioral change is caught immediately.

Tests are self-contained — all fixtures are inline strings. No external
fixture files are required.

Run with:
    cd ~/projects/tailor-resume
    python -m pytest tests/test_profile_extractor_regression.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path


# Make scripts importable regardless of how pytest is invoked
sys.path.insert(
    0,
    str(Path(__file__).parent.parent / ".claude/skills/tailor-resume/scripts"),
)

from profile_extractor import (
    auto_detect_format,
    parse_blob,
    parse_latex,
    parse_markdown,
)
from resume_types import Bullet, Profile, Project, Role, profile_to_dict


# ---------------------------------------------------------------------------
# Inline fixture constants
# ---------------------------------------------------------------------------

# A standard Jake-template LaTeX resume section for experience
SAMPLE_LATEX_EXPERIENCE = r"""
\section{Experience}
  \resumeSubHeadingListStart
    \resumeSubheading
      {Senior Data Engineer}{Jan 2022 -- Present}
      {Acme Corp}{Austin, TX}
      \resumeItemListStart
        \resumeItem{Built Spark pipelines processing 5TB/day, reducing latency by 40\%}
        \resumeItem{Led team of 4 engineers across two time zones}
      \resumeItemListEnd
    \resumeSubheading
      {Data Engineer}{Jun 2019 -- Dec 2021}
      {Beta Systems}{New York, NY}
      \resumeItemListStart
        \resumeItem{Designed partitioned Delta Lake tables cutting query time by 60\%}
      \resumeItemListEnd
  \resumeSubHeadingListEnd
"""

# LaTeX with a nested \href inside \resumeItem
SAMPLE_LATEX_HREF = r"""
\section{Experience}
  \resumeSubHeadingListStart
    \resumeSubheading
      {ML Engineer}{Mar 2023 -- Present}
      {DeepMind Co}{London, UK}
      \resumeItemListStart
        \resumeItem{Published at \href{https://arxiv.org/abs/1234}{NeurIPS 2023}, achieving SOTA on 3 benchmarks}
      \resumeItemListEnd
  \resumeSubHeadingListEnd
"""

# LaTeX with a \resumeProjectHeading
SAMPLE_LATEX_PROJECTS = r"""
\section{Projects}
  \resumeSubHeadingListStart
    \resumeProjectHeading
      {\textbf{Portfolio Risk Engine} $|$ \emph{Python, Kafka, Spark}}{Jan 2023 -- Mar 2023}
      \resumeItemListStart
        \resumeItem{Streamed 1M market events/day through Kafka topics with zero data loss}
        \resumeItem{Reduced P99 latency from 900ms to 45ms using async consumers}
      \resumeItemListEnd
    \resumeProjectHeading
      {\textbf{Fraud Detection ML} $|$ \emph{Airflow, MLflow, XGBoost}}{2022}
      \resumeItemListStart
        \resumeItem{Trained XGBoost model achieving 96\% AUC on hold-out set}
      \resumeItemListEnd
  \resumeSubHeadingListEnd
"""

# LaTeX with a Technical Skills section using \textbf{Category}{: item1, item2}
SAMPLE_LATEX_SKILLS = r"""
\section{Technical Skills}
 \begin{itemize}
    \small{\item{
     \textbf{Languages}{: Python, SQL, Bash, Scala} \\
     \textbf{Cloud \& Data}{: Spark, Kafka, Databricks, Azure} \\
     \textbf{DevOps}{: Docker, Kubernetes, Terraform} \\
    }}
 \end{itemize}
"""

# LaTeX with Education
SAMPLE_LATEX_EDUCATION = r"""
\section{Education}
  \resumeSubHeadingListStart
    \resumeSubheading
      {University of Texas at Austin}{Austin, TX}
      {Master of Science in Computer Science}{Aug 2020 -- May 2022}
  \resumeSubHeadingListEnd
"""

# Combined full LaTeX resume
FULL_LATEX = SAMPLE_LATEX_EXPERIENCE + SAMPLE_LATEX_PROJECTS + SAMPLE_LATEX_EDUCATION + SAMPLE_LATEX_SKILLS

# Standard markdown resume
SAMPLE_MARKDOWN = """\
## Experience

**Senior Data Engineer** | DataWorks Inc | Jan 2022 - Present
- Built governed semantic layer on Databricks, cutting metric discrepancies from 12/week to zero
- Owned CI/CD via Azure DevOps, compressing deployments from 8 weeks to 6 days

**Data Engineer** | Acme Analytics | Jun 2020 - Dec 2021
- Designed partitioned Delta Lake tables, cutting query time by 60%
- Migrated on-prem ETL to Azure Data Factory, reducing maintenance overhead

## Projects

**Portfolio Dashboard** | Streamlit, Python | 2023
- Built real-time analytics dashboard serving 500 concurrent users

## Skills

Python, SQL, Spark, Airflow, Delta Lake, Kafka, Docker
"""

# Plain text blob (structured with Company:/Title:/Dates: labels)
SAMPLE_BLOB = """\
Company: Acme Corp
Title: Senior Data Engineer
Dates: Jan 2022 - Present
- Built Spark pipelines processing 5TB/day, reducing latency by 40%
- Led team of 4 engineers

Company: Beta Systems
Title: Data Engineer
Dates: Jun 2019 - Dec 2021
- Designed partitioned tables cutting query time by 60%
"""

# Blob with a summary paragraph and a skills line
SAMPLE_BLOB_WITH_SKILLS = """\
Company: TechCo
Title: Staff Engineer
Dates: 2020 - Present
- Built distributed systems at scale
"""


# ===========================================================================
# Group 1 — LaTeX parsing: \resumeSubheading → Role fields
# ===========================================================================

class TestLatexSubheadingToRole:
    """Pins the field-level mapping from \resumeSubheading to Role attributes."""

    def test_first_role_title(self):
        profile = parse_latex(SAMPLE_LATEX_EXPERIENCE)
        assert profile.experience[0].title == "Senior Data Engineer"

    def test_first_role_company(self):
        profile = parse_latex(SAMPLE_LATEX_EXPERIENCE)
        assert profile.experience[0].company == "Acme Corp"

    def test_first_role_location(self):
        profile = parse_latex(SAMPLE_LATEX_EXPERIENCE)
        assert profile.experience[0].location == "Austin, TX"

    def test_first_role_start(self):
        profile = parse_latex(SAMPLE_LATEX_EXPERIENCE)
        # _clean_latex converts -- to – before _parse_dates splits on it
        assert "Jan 2022" in profile.experience[0].start

    def test_first_role_end(self):
        profile = parse_latex(SAMPLE_LATEX_EXPERIENCE)
        # "Present" is the end date after parsing "Jan 2022 – Present"
        assert "Present" in profile.experience[0].end

    def test_second_role_extracted(self):
        profile = parse_latex(SAMPLE_LATEX_EXPERIENCE)
        assert len(profile.experience) == 2

    def test_second_role_title(self):
        profile = parse_latex(SAMPLE_LATEX_EXPERIENCE)
        assert profile.experience[1].title == "Data Engineer"

    def test_second_role_company(self):
        profile = parse_latex(SAMPLE_LATEX_EXPERIENCE)
        assert profile.experience[1].company == "Beta Systems"

    def test_experience_list_is_role_objects(self):
        profile = parse_latex(SAMPLE_LATEX_EXPERIENCE)
        for role in profile.experience:
            assert isinstance(role, Role)


# ===========================================================================
# Group 2 — LaTeX parsing: \resumeItem → Bullet
# ===========================================================================

class TestLatexResumeItemToBullet:
    """Pins bullet attachment, text cleaning, and Bullet field structure."""

    def test_first_role_has_two_bullets(self):
        profile = parse_latex(SAMPLE_LATEX_EXPERIENCE)
        assert len(profile.experience[0].bullets) == 2

    def test_second_role_has_one_bullet(self):
        profile = parse_latex(SAMPLE_LATEX_EXPERIENCE)
        assert len(profile.experience[1].bullets) == 1

    def test_bullet_text_verbatim_content(self):
        """Bullet text should contain the human-readable content exactly."""
        profile = parse_latex(SAMPLE_LATEX_EXPERIENCE)
        first_bullet = profile.experience[0].bullets[0].text
        assert "5TB/day" in first_bullet
        assert "40%" in first_bullet

    def test_latex_percent_escape_cleaned(self):
        """\\% in source must be rendered as % in bullet text."""
        profile = parse_latex(SAMPLE_LATEX_EXPERIENCE)
        first_bullet = profile.experience[0].bullets[0].text
        assert "\\%" not in first_bullet
        assert "%" in first_bullet

    def test_bullet_is_bullet_object(self):
        profile = parse_latex(SAMPLE_LATEX_EXPERIENCE)
        for role in profile.experience:
            for bullet in role.bullets:
                assert isinstance(bullet, Bullet)

    def test_bullet_has_evidence_source(self):
        profile = parse_latex(SAMPLE_LATEX_EXPERIENCE, source="test_source")
        assert profile.experience[0].bullets[0].evidence_source == "test_source"

    def test_bullet_confidence_is_valid(self):
        profile = parse_latex(SAMPLE_LATEX_EXPERIENCE)
        for role in profile.experience:
            for bullet in role.bullets:
                assert bullet.confidence in ("high", "medium", "low")

    def test_bullet_metrics_extracted_for_quantified_bullet(self):
        """A bullet with a percentage should have non-empty metrics."""
        profile = parse_latex(SAMPLE_LATEX_EXPERIENCE)
        first_bullet = profile.experience[0].bullets[0]
        assert len(first_bullet.metrics) >= 1

    def test_bullet_tools_extracted(self):
        """A bullet mentioning Spark should have 'Spark' in tools."""
        profile = parse_latex(SAMPLE_LATEX_EXPERIENCE)
        first_bullet = profile.experience[0].bullets[0]
        tool_names = [t.lower() for t in first_bullet.tools]
        assert "spark" in tool_names


# ===========================================================================
# Group 3 — LaTeX parsing: nested braces in \resumeItem (\href unwrapping)
# ===========================================================================

class TestLatexNestedBracesInResumeItem:
    """Pins the behavior of _clean_latex on nested macros inside \resumeItem."""

    def test_href_url_not_in_bullet_text(self):
        profile = parse_latex(SAMPLE_LATEX_HREF)
        bullet_text = profile.experience[0].bullets[0].text
        assert "https://arxiv.org" not in bullet_text

    def test_href_label_in_bullet_text(self):
        """\\href{url}{label} should render as label only."""
        profile = parse_latex(SAMPLE_LATEX_HREF)
        bullet_text = profile.experience[0].bullets[0].text
        assert "NeurIPS 2023" in bullet_text

    def test_bullet_text_has_no_backslash_commands(self):
        """No LaTeX backslash commands should survive in the cleaned bullet text."""
        profile = parse_latex(SAMPLE_LATEX_HREF)
        bullet_text = profile.experience[0].bullets[0].text
        assert "\\href" not in bullet_text

    def test_remaining_text_preserved(self):
        """Text surrounding the \href should be preserved."""
        profile = parse_latex(SAMPLE_LATEX_HREF)
        bullet_text = profile.experience[0].bullets[0].text
        assert "achieving SOTA" in bullet_text


# ===========================================================================
# Group 4 — LaTeX parsing: \resumeProjectHeading → Project (not Role)
# ===========================================================================

class TestLatexProjectHeadingToProject:
    """Pins that \resumeProjectHeading is parsed as Project, not Role."""

    def test_projects_not_in_experience(self):
        profile = parse_latex(SAMPLE_LATEX_PROJECTS)
        assert len(profile.experience) == 0

    def test_project_count(self):
        profile = parse_latex(SAMPLE_LATEX_PROJECTS)
        assert len(profile.projects) == 2

    def test_first_project_name(self):
        profile = parse_latex(SAMPLE_LATEX_PROJECTS)
        assert profile.projects[0].name == "Portfolio Risk Engine"

    def test_second_project_name(self):
        profile = parse_latex(SAMPLE_LATEX_PROJECTS)
        assert profile.projects[1].name == "Fraud Detection ML"

    def test_project_tech_list_populated(self):
        """The pipe-separated tech stack after | should be split into a list."""
        profile = parse_latex(SAMPLE_LATEX_PROJECTS)
        tech = profile.projects[0].tech
        assert isinstance(tech, list)
        assert len(tech) >= 1

    def test_project_tech_contains_python(self):
        profile = parse_latex(SAMPLE_LATEX_PROJECTS)
        tech_lower = [t.lower() for t in profile.projects[0].tech]
        assert "python" in tech_lower

    def test_project_tech_contains_kafka(self):
        profile = parse_latex(SAMPLE_LATEX_PROJECTS)
        tech_lower = [t.lower() for t in profile.projects[0].tech]
        assert "kafka" in tech_lower

    def test_project_is_project_object(self):
        profile = parse_latex(SAMPLE_LATEX_PROJECTS)
        for proj in profile.projects:
            assert isinstance(proj, Project)

    def test_first_project_has_two_bullets(self):
        profile = parse_latex(SAMPLE_LATEX_PROJECTS)
        assert len(profile.projects[0].bullets) == 2

    def test_second_project_has_one_bullet(self):
        profile = parse_latex(SAMPLE_LATEX_PROJECTS)
        assert len(profile.projects[1].bullets) == 1

    def test_project_bullet_text_preserved(self):
        """Bullet text for projects must contain the original content."""
        profile = parse_latex(SAMPLE_LATEX_PROJECTS)
        texts = [b.text for b in profile.projects[0].bullets]
        assert any("1M market events" in t for t in texts)

    def test_project_date_field(self):
        """The second arg to \resumeProjectHeading becomes the date field."""
        profile = parse_latex(SAMPLE_LATEX_PROJECTS)
        # Both projects have dates; first one has a range
        assert profile.projects[0].date != "" or profile.projects[1].date != ""


# ===========================================================================
# Group 5 — LaTeX parsing: Skills section → dict keyed by category
# ===========================================================================

class TestLatexSkillsSection:
    """Pins skills parsing from \\textbf{Category}{: item1, item2} format."""

    def test_skills_list_is_non_empty(self):
        profile = parse_latex(SAMPLE_LATEX_SKILLS)
        assert len(profile.skills) > 0

    def test_skills_contain_python(self):
        skill_lower = [s.lower() for s in parse_latex(SAMPLE_LATEX_SKILLS).skills]
        assert "python" in skill_lower

    def test_skills_contain_spark(self):
        skill_lower = [s.lower() for s in parse_latex(SAMPLE_LATEX_SKILLS).skills]
        assert "spark" in skill_lower

    def test_skills_contain_docker(self):
        skill_lower = [s.lower() for s in parse_latex(SAMPLE_LATEX_SKILLS).skills]
        assert "docker" in skill_lower

    def test_skills_are_deduped(self):
        profile = parse_latex(SAMPLE_LATEX_SKILLS)
        assert len(profile.skills) == len(set(profile.skills))

    def test_skills_are_strings(self):
        profile = parse_latex(SAMPLE_LATEX_SKILLS)
        for s in profile.skills:
            assert isinstance(s, str)

    def test_category_labels_not_in_skills(self):
        """Category names like 'Languages' should NOT appear in the skills list."""
        profile = parse_latex(SAMPLE_LATEX_SKILLS)
        skill_lower = [s.lower() for s in profile.skills]
        # "Languages" is a category label, not a skill
        assert "languages" not in skill_lower


# ===========================================================================
# Group 6 — LaTeX parsing: Education section
# ===========================================================================

class TestLatexEducationSection:
    """Pins education parsing from \resumeSubheading in \section{Education}."""

    def test_education_count(self):
        profile = parse_latex(SAMPLE_LATEX_EDUCATION)
        assert len(profile.education) == 1

    def test_education_institution(self):
        profile = parse_latex(SAMPLE_LATEX_EDUCATION)
        assert "University of Texas" in profile.education[0]["institution"]

    def test_education_degree(self):
        profile = parse_latex(SAMPLE_LATEX_EDUCATION)
        assert "Computer Science" in profile.education[0]["degree"]

    def test_education_location(self):
        profile = parse_latex(SAMPLE_LATEX_EDUCATION)
        assert "Austin" in profile.education[0]["location"]

    def test_education_dates_present(self):
        profile = parse_latex(SAMPLE_LATEX_EDUCATION)
        assert profile.education[0]["dates"] != ""

    def test_education_is_dict(self):
        """Education entries are dicts, not dataclass objects."""
        profile = parse_latex(SAMPLE_LATEX_EDUCATION)
        assert isinstance(profile.education[0], dict)

    def test_education_dict_has_required_keys(self):
        profile = parse_latex(SAMPLE_LATEX_EDUCATION)
        entry = profile.education[0]
        assert "institution" in entry
        assert "degree" in entry
        assert "dates" in entry
        assert "location" in entry


# ===========================================================================
# Group 7 — Markdown parsing: sections → correct output types
# ===========================================================================

class TestMarkdownParsing:
    """Pins markdown parsing: ## headings, **Title** | Company | Date, - bullets."""

    def test_experience_role_count(self):
        profile = parse_markdown(SAMPLE_MARKDOWN)
        assert len(profile.experience) == 2

    def test_first_role_title(self):
        profile = parse_markdown(SAMPLE_MARKDOWN)
        assert profile.experience[0].title == "Senior Data Engineer"

    def test_first_role_company(self):
        profile = parse_markdown(SAMPLE_MARKDOWN)
        assert profile.experience[0].company == "DataWorks Inc"

    def test_first_role_start_date(self):
        """The third field in **Title** | Company | Date becomes the start date."""
        profile = parse_markdown(SAMPLE_MARKDOWN)
        # parse_markdown stores the third capture group in `start`; end is always ""
        assert "Jan 2022" in profile.experience[0].start

    def test_first_role_end_is_empty(self):
        """parse_markdown does not parse date ranges — end is always empty string."""
        profile = parse_markdown(SAMPLE_MARKDOWN)
        assert profile.experience[0].end == ""

    def test_first_role_location_is_empty(self):
        """parse_markdown does not populate location — always empty."""
        profile = parse_markdown(SAMPLE_MARKDOWN)
        assert profile.experience[0].location == ""

    def test_first_role_bullet_count(self):
        profile = parse_markdown(SAMPLE_MARKDOWN)
        assert len(profile.experience[0].bullets) == 2

    def test_bullet_text_verbatim(self):
        profile = parse_markdown(SAMPLE_MARKDOWN)
        texts = [b.text for b in profile.experience[0].bullets]
        assert any("Databricks" in t for t in texts)

    def test_skills_flat_list(self):
        """## Skills section with comma-separated values → flat list in profile."""
        profile = parse_markdown(SAMPLE_MARKDOWN)
        skill_lower = [s.lower() for s in profile.skills]
        assert "python" in skill_lower
        assert "spark" in skill_lower
        assert "kafka" in skill_lower

    def test_projects_not_in_experience(self):
        """## Projects section is NOT parsed by parse_markdown (no project logic)."""
        profile = parse_markdown(SAMPLE_MARKDOWN)
        # parse_markdown has no project-header recognition — projects stay empty
        assert profile.projects == []

    def test_empty_text_returns_empty_profile(self):
        profile = parse_markdown("")
        assert profile.experience == []
        assert profile.skills == []


# ===========================================================================
# Group 8 — Markdown parsing: ## heading with @ separator
# ===========================================================================

class TestMarkdownAtSeparator:
    """Pins that both | and @ work as field separators in the experience pattern."""

    SAMPLE = """\
## Experience

**ML Engineer** @ OpenAI @ Mar 2023 - Present
- Fine-tuned GPT-4 on 10M instruction samples, improving MMLU by 8%
"""

    def test_at_separator_role_title(self):
        profile = parse_markdown(self.SAMPLE)
        assert len(profile.experience) >= 1
        assert profile.experience[0].title == "ML Engineer"

    def test_at_separator_role_company(self):
        profile = parse_markdown(self.SAMPLE)
        assert profile.experience[0].company == "OpenAI"


# ===========================================================================
# Group 9 — Blob parsing: structured labels → Role
# ===========================================================================

class TestBlobParsing:
    """Pins parse_blob behavior with Company:/Title:/Dates: structured input."""

    def test_blob_extracts_two_roles(self):
        profile = parse_blob(SAMPLE_BLOB)
        assert len(profile.experience) == 2

    def test_first_role_company(self):
        profile = parse_blob(SAMPLE_BLOB)
        assert profile.experience[0].company == "Acme Corp"

    def test_first_role_title(self):
        profile = parse_blob(SAMPLE_BLOB)
        assert profile.experience[0].title == "Senior Data Engineer"

    def test_first_role_start_date(self):
        profile = parse_blob(SAMPLE_BLOB)
        assert "Jan 2022" in profile.experience[0].start

    def test_first_role_end_date(self):
        profile = parse_blob(SAMPLE_BLOB)
        assert "Present" in profile.experience[0].end

    def test_first_role_bullet_count(self):
        profile = parse_blob(SAMPLE_BLOB)
        assert len(profile.experience[0].bullets) == 2

    def test_bullet_text_stripped_of_dash(self):
        """The leading '- ' prefix must be stripped from bullet text."""
        profile = parse_blob(SAMPLE_BLOB)
        bullet_text = profile.experience[0].bullets[0].text
        assert not bullet_text.startswith("- ")
        assert "Spark pipelines" in bullet_text

    def test_empty_blob_returns_empty_profile(self):
        profile = parse_blob("")
        assert profile.experience == []

    def test_blob_skills_not_populated(self):
        """parse_blob has no skills-section logic — skills stays empty."""
        profile = parse_blob(SAMPLE_BLOB)
        assert profile.skills == []

    def test_blob_source_tagged_in_bullets(self):
        profile = parse_blob(SAMPLE_BLOB, source="my_blob_source")
        for role in profile.experience:
            for bullet in role.bullets:
                assert bullet.evidence_source == "my_blob_source"


# ===========================================================================
# Group 10 — Format auto-detection
# ===========================================================================

class TestAutoDetectFormat:
    """Pins the detection heuristics in auto_detect_format."""

    def test_documentclass_detected_as_latex(self):
        text = r"\documentclass[letterpaper]{article}" + "\n\\begin{document}\\end{document}"
        assert auto_detect_format(text) == "latex"

    def test_resumesubheading_detected_as_latex(self):
        text = r"\resumeSubheading{Title}{Dates}{Company}{Location}"
        assert auto_detect_format(text) == "latex"

    def test_resumeitem_alone_detected_as_latex(self):
        text = r"\resumeItem{Built something important}"
        assert auto_detect_format(text) == "latex"

    def test_double_hash_heading_detected_as_markdown(self):
        text = "## Experience\n**Engineer** | Acme | 2022\n- Built thing"
        assert auto_detect_format(text) == "markdown"

    def test_single_hash_heading_detected_as_markdown(self):
        text = "# Resume\n## Skills\nPython, SQL"
        assert auto_detect_format(text) == "markdown"

    def test_triple_hash_heading_detected_as_markdown(self):
        text = "### Senior Engineer\n- Did things"
        assert auto_detect_format(text) == "markdown"

    def test_generic_blob_returns_blob(self):
        text = "Senior Data Engineer at Acme Corp from 2020 to 2022"
        assert auto_detect_format(text) == "blob"

    def test_empty_string_returns_blob(self):
        assert auto_detect_format("") == "blob"

    def test_latex_with_markdown_chars_still_latex(self):
        """LaTeX markers take priority — if both present, latex wins."""
        text = r"\resumeItem{Used ## as a comment}" + "\n## Experience"
        # documentclass / resumeItem checks happen before markdown check
        assert auto_detect_format(text) == "latex"


# ===========================================================================
# Group 11 — Profile output structure: profile_to_dict
# ===========================================================================

class TestProfileToDict:
    """Pins the JSON-serializable dict structure returned by profile_to_dict."""

    def test_returns_dict(self):
        profile = parse_latex(FULL_LATEX)
        d = profile_to_dict(profile)
        assert isinstance(d, dict)

    def test_top_level_keys(self):
        profile = parse_latex(FULL_LATEX)
        d = profile_to_dict(profile)
        assert set(d.keys()) == {"experience", "projects", "skills", "education", "certifications"}

    def test_experience_is_list(self):
        profile = parse_latex(FULL_LATEX)
        d = profile_to_dict(profile)
        assert isinstance(d["experience"], list)

    def test_experience_entry_has_role_fields(self):
        profile = parse_latex(FULL_LATEX)
        d = profile_to_dict(profile)
        entry = d["experience"][0]
        assert "title" in entry
        assert "company" in entry
        assert "start" in entry
        assert "end" in entry
        assert "location" in entry
        assert "bullets" in entry

    def test_bullet_in_dict_has_expected_fields(self):
        profile = parse_latex(FULL_LATEX)
        d = profile_to_dict(profile)
        bullet = d["experience"][0]["bullets"][0]
        assert "text" in bullet
        assert "evidence_source" in bullet
        assert "confidence" in bullet
        assert "metrics" in bullet
        assert "tools" in bullet

    def test_projects_is_list(self):
        profile = parse_latex(FULL_LATEX)
        d = profile_to_dict(profile)
        assert isinstance(d["projects"], list)

    def test_project_entry_has_name_tech_bullets(self):
        profile = parse_latex(FULL_LATEX)
        d = profile_to_dict(profile)
        proj = d["projects"][0]
        assert "name" in proj
        assert "tech" in proj
        assert "bullets" in proj

    def test_skills_is_list_of_strings(self):
        profile = parse_latex(FULL_LATEX)
        d = profile_to_dict(profile)
        for s in d["skills"]:
            assert isinstance(s, str)

    def test_education_is_list_of_dicts(self):
        profile = parse_latex(FULL_LATEX)
        d = profile_to_dict(profile)
        for e in d["education"]:
            assert isinstance(e, dict)

    def test_profile_to_dict_is_json_serializable(self):
        """profile_to_dict output must be fully JSON-serializable."""
        import json
        profile = parse_latex(FULL_LATEX)
        d = profile_to_dict(profile)
        # Should not raise
        serialized = json.dumps(d)
        assert isinstance(serialized, str)


# ===========================================================================
# Group 12 — Edge cases: empty inputs, missing dates, special characters
# ===========================================================================

class TestEdgeCases:
    """Pins behavior on malformed or minimal inputs."""

    def test_parse_latex_empty_string(self):
        profile = parse_latex("")
        assert isinstance(profile, Profile)
        assert profile.experience == []
        assert profile.projects == []
        assert profile.skills == []

    def test_parse_markdown_empty_string(self):
        profile = parse_markdown("")
        assert isinstance(profile, Profile)
        assert profile.experience == []

    def test_parse_blob_empty_string(self):
        profile = parse_blob("")
        assert isinstance(profile, Profile)
        assert profile.experience == []

    def test_parse_latex_missing_fourth_arg(self):
        """\resumeSubheading with only 3 args — location defaults to empty string."""
        tex = r"""
\section{Experience}
  \resumeSubheading{Data Engineer}{2022 -- Present}{Acme}
"""
        profile = parse_latex(tex)
        # Should not crash; role should be created with empty location
        assert len(profile.experience) == 1
        assert profile.experience[0].location == ""

    def test_parse_latex_role_with_no_bullets(self):
        """A \resumeSubheading with no \resumeItem entries should have empty bullets."""
        tex = r"""
\section{Experience}
  \resumeSubheading{Data Engineer}{2022 -- Present}{Acme}{Remote}
"""
        profile = parse_latex(tex)
        assert profile.experience[0].bullets == []

    def test_parse_latex_special_ampersand(self):
        """\\& in LaTeX should become & in cleaned text."""
        tex = r"""
\section{Experience}
  \resumeSubheading{Data Engineer}{2022 -- Present}{Missouri S\&T}{Rolla, MO}
"""
        profile = parse_latex(tex)
        assert "Missouri" in profile.experience[0].company
        assert "\\&" not in profile.experience[0].company

    def test_parse_markdown_role_without_bullets(self):
        """A role line with no following bullet lines should produce a role with empty bullets."""
        md = "## Experience\n\n**Engineer** | Acme | 2022\n\n## Skills\nPython\n"
        profile = parse_markdown(md)
        assert len(profile.experience) >= 1
        assert profile.experience[0].bullets == []

    def test_parse_blob_role_without_dates(self):
        """A blob role without a Dates: line should have empty start/end."""
        blob = "Company: Orphan Corp\nTitle: Software Engineer\n- Did things\n"
        profile = parse_blob(blob)
        assert len(profile.experience) == 1
        assert profile.experience[0].start == ""
        assert profile.experience[0].end == ""

    def test_parse_latex_bullet_with_dollar_sign(self):
        """Dollar sign in bullet text should survive cleaning."""
        tex = r"""
\section{Experience}
  \resumeSubheading{Engineer}{2022 -- Present}{TechCo}{Remote}
    \resumeItemListStart
      \resumeItem{Saved \$4,100/month in compute costs via ETL refactor}
    \resumeItemListEnd
"""
        profile = parse_latex(tex)
        bullet_text = profile.experience[0].bullets[0].text
        assert "$" in bullet_text
        assert "4,100" in bullet_text

    def test_parse_latex_no_sections_produces_empty_profile(self):
        """LaTeX with no \\section{} commands produces an empty Profile."""
        tex = r"\begin{document}\end{document}"
        profile = parse_latex(tex)
        assert profile.experience == []
        assert profile.education == []
        assert profile.skills == []

    def test_parse_markdown_bullet_with_backtick_code(self):
        """Bullets with backtick code spans should be preserved verbatim."""
        md = "## Experience\n\n**Engineer** | Acme | 2022\n- Used `dbt run --select +model` in CI\n"
        profile = parse_markdown(md)
        bullet_text = profile.experience[0].bullets[0].text
        assert "dbt" in bullet_text

    def test_profile_to_dict_on_empty_profile(self):
        """profile_to_dict on a bare Profile() should return empty lists."""
        import json
        d = profile_to_dict(Profile())
        assert d["experience"] == []
        assert d["projects"] == []
        assert d["skills"] == []
        assert d["education"] == []
        assert d["certifications"] == []
        # Must still be JSON-serializable
        json.dumps(d)

    def test_parse_latex_multiple_bullets_all_attached_correctly(self):
        """All bullets in a multi-role experience section are attached to the right roles."""
        profile = parse_latex(SAMPLE_LATEX_EXPERIENCE)
        # Role 0 should have exactly 2 bullets, role 1 should have exactly 1
        assert len(profile.experience[0].bullets) == 2
        assert len(profile.experience[1].bullets) == 1
        # Confirm content is in the right role
        role1_texts = [b.text for b in profile.experience[0].bullets]
        assert any("5TB/day" in t for t in role1_texts)
        role2_texts = [b.text for b in profile.experience[1].bullets]
        assert any("Delta Lake" in t for t in role2_texts)


# ===========================================================================
# Group 13 — Behavioral quirks: document what the parser actually does
# ===========================================================================

class TestBehavioralQuirks:
    """
    Document known behavioral characteristics that might look surprising.
    These tests exist to catch regressions in quirky-but-correct behavior.
    """

    def test_parse_markdown_end_date_is_always_empty_string(self):
        """parse_markdown does not split date ranges — end is always ''."""
        md = "## Experience\n\n**Engineer** | Acme | Jan 2022 - Present\n- Built things\n"
        profile = parse_markdown(md)
        assert profile.experience[0].end == ""

    def test_parse_markdown_full_date_range_stored_in_start(self):
        """When markdown has a date range, the whole string goes into start."""
        md = "## Experience\n\n**Engineer** | Acme | Jan 2022 - Present\n- Built things\n"
        profile = parse_markdown(md)
        # The full date string (range) lands in .start since parse_markdown
        # captures group(3) directly without calling _parse_dates
        assert "Jan 2022" in profile.experience[0].start

    def test_parse_latex_double_dash_becomes_en_dash_in_start_end(self):
        """-- in LaTeX dates is converted to – by _clean_latex before _parse_dates splits."""
        tex = r"""
\section{Experience}
  \resumeSubheading{Engineer}{Jan 2022 -- Present}{Acme}{Remote}
"""
        profile = parse_latex(tex)
        # After clean: "Jan 2022 – Present"; _parse_dates splits on " – "
        assert profile.experience[0].start == "Jan 2022"
        assert profile.experience[0].end == "Present"

    def test_parse_latex_skills_category_label_stripped(self):
        """The \\textbf{Category} label is not added to skills — only the values are."""
        profile = parse_latex(SAMPLE_LATEX_SKILLS)
        # "Languages", "Cloud & Data", "DevOps" are category labels — none should appear
        skill_lower = [s.lower() for s in profile.skills]
        assert "devops" not in skill_lower

    def test_parse_blob_star_prefix_also_recognized_as_bullet(self):
        """Bullets starting with * (not just -) are parsed correctly."""
        blob = "Company: StarCo\nTitle: Engineer\nDates: 2022 - 2024\n* Built a pipeline\n"
        profile = parse_blob(blob)
        assert len(profile.experience[0].bullets) == 1
        assert "Built a pipeline" in profile.experience[0].bullets[0].text

    def test_parse_latex_project_date_field_populated(self):
        """The second argument to \\resumeProjectHeading is stored in project.date."""
        profile = parse_latex(SAMPLE_LATEX_PROJECTS)
        # First project: "Jan 2023 -- Mar 2023" (gets cleaned to en-dash form)
        assert profile.projects[0].date != ""

    def test_profile_experience_order_matches_document_order(self):
        """Roles must be appended in document order, not reversed."""
        profile = parse_latex(SAMPLE_LATEX_EXPERIENCE)
        assert profile.experience[0].title == "Senior Data Engineer"
        assert profile.experience[1].title == "Data Engineer"

    def test_parse_blob_bullets_not_attached_before_first_company(self):
        """Bullet lines appearing before any Company: header are ignored."""
        blob = "- Orphan bullet line\nCompany: Acme\nTitle: Eng\n- Real bullet\n"
        profile = parse_blob(blob)
        # Only one role
        assert len(profile.experience) == 1
        # And that role only has the real bullet
        assert len(profile.experience[0].bullets) == 1
        assert "Real bullet" in profile.experience[0].bullets[0].text
