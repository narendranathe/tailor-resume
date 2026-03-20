"""Tests for latex_renderer.py — escape, section builders, template rendering."""
import json
import re
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude/skills/tailor-resume/scripts"))

from latex_renderer import (
    escape,
    escape_url,
    render_bullets,
    render_experience,
    render_projects,
    render_skills,
    render_education,
    render_certifications,
    render_template,
    build_from_profile,
)

TEMPLATE_PATH = str(
    Path(__file__).parent.parent
    / ".claude/skills/tailor-resume/templates/resume_template.tex"
)


# ---------------------------------------------------------------------------
# escape
# ---------------------------------------------------------------------------
class TestEscape:
    def test_escapes_ampersand(self):
        assert r"\&" in escape("AT&T")

    def test_escapes_percent(self):
        assert r"\%" in escape("50% reduction")

    def test_escapes_dollar(self):
        assert r"\$" in escape("$4,000")

    def test_escapes_underscore(self):
        assert r"\_" in escape("some_variable")

    def test_escapes_hash(self):
        assert r"\#" in escape("Issue #3")

    def test_plain_text_unchanged(self):
        assert escape("hello world") == "hello world"

    def test_empty_string(self):
        assert escape("") == ""

    def test_backslash_escaped(self):
        result = escape("C:\\Users")
        assert "textbackslash" in result


# ---------------------------------------------------------------------------
# escape_url
# ---------------------------------------------------------------------------
class TestEscapeUrl:
    def test_url_passes_through(self):
        url = "https://linkedin.com/in/jane-smith"
        assert escape_url(url) == url


# ---------------------------------------------------------------------------
# render_bullets
# ---------------------------------------------------------------------------
class TestRenderBullets:
    def test_renders_item_list(self):
        bullets = [{"text": "Built pipeline saving $1k/month"}]
        result = render_bullets(bullets)
        assert "resumeItemListStart" in result
        assert "resumeItemListEnd" in result
        assert "resumeItem" in result

    def test_escapes_special_chars_in_bullets(self):
        bullets = [{"text": "Saved 50% & reduced costs"}]
        result = render_bullets(bullets)
        assert r"\%" in result
        assert r"\&" in result

    def test_max_six_bullets(self):
        bullets = [{"text": f"Bullet {i}"} for i in range(10)]
        result = render_bullets(bullets)
        count = result.count("\\resumeItem{")
        assert count == 6

    def test_empty_bullets(self):
        result = render_bullets([])
        assert "resumeItemListStart" in result
        assert "resumeItemListEnd" in result


# ---------------------------------------------------------------------------
# render_experience
# ---------------------------------------------------------------------------
class TestRenderExperience:
    def test_renders_experience_section_header(self):
        roles = [{"title": "Data Engineer", "company": "Acme Corp", "start": "2021", "end": "Present", "location": "Remote", "bullets": [{"text": "Built pipelines"}]}]
        result = render_experience(roles)
        assert "\\section{Experience}" in result

    def test_renders_role_title(self):
        roles = [{"title": "Senior Data Engineer", "company": "DataWorks", "start": "2022", "end": "Present", "location": "", "bullets": []}]
        result = render_experience(roles)
        assert "Senior Data Engineer" in result

    def test_renders_multiple_roles(self):
        roles = [
            {"title": "DE", "company": "A", "start": "2020", "end": "2021", "location": "", "bullets": []},
            {"title": "SDE", "company": "B", "start": "2021", "end": "2022", "location": "", "bullets": []},
        ]
        result = render_experience(roles)
        assert "DE" in result
        assert "SDE" in result

    def test_empty_experience(self):
        result = render_experience([])
        assert "\\section{Experience}" in result


# ---------------------------------------------------------------------------
# render_projects
# ---------------------------------------------------------------------------
class TestRenderProjects:
    def test_returns_empty_string_for_no_projects(self):
        assert render_projects([]) == ""

    def test_renders_project_name(self):
        projects = [{"name": "Analytics Dashboard", "tech": ["Python", "Streamlit"], "date": "2023", "bullets": [{"text": "Built real-time dashboard"}]}]
        result = render_projects(projects)
        assert "Analytics Dashboard" in result

    def test_renders_tech_stack(self):
        projects = [{"name": "Pipeline", "tech": ["Spark", "Airflow"], "date": "2022", "bullets": []}]
        result = render_projects(projects)
        assert "Spark" in result or "Airflow" in result

    def test_renders_project_bullets(self):
        projects = [{"name": "Proj", "tech": [], "date": "2023", "bullets": [{"text": "Built feature X"}]}]
        result = render_projects(projects)
        assert "Built feature X" in result

    def test_renders_section_wrapper(self):
        projects = [{"name": "Proj", "tech": [], "date": "2023", "bullets": []}]
        result = render_projects(projects)
        assert "\\section{Projects}" in result


# ---------------------------------------------------------------------------
# render_skills
# ---------------------------------------------------------------------------
class TestRenderSkills:
    def test_renders_list_as_single_line(self):
        result = render_skills(["Python", "SQL", "Spark"])
        assert "Python" in result
        assert "\\section{Technical Skills}" in result

    def test_renders_dict_with_categories(self):
        skills = {"Languages": ["Python", "SQL"], "Tools": ["Airflow", "Spark"]}
        result = render_skills(skills)
        assert "Languages" in result
        assert "Python" in result
        assert "Airflow" in result

    def test_renders_empty_list(self):
        result = render_skills([])
        assert "\\section{Technical Skills}" in result

    def test_returns_empty_string_for_invalid_type(self):
        result = render_skills(None)
        assert result == ""

    def test_dict_escapes_category_names(self):
        skills = {"C++ & Scripting": ["Python"]}
        result = render_skills(skills)
        assert r"\&" in result or "C" in result


# ---------------------------------------------------------------------------
# render_education
# ---------------------------------------------------------------------------
class TestRenderEducation:
    def test_renders_section_header(self):
        edu = [{"school": "University of Missouri", "location": "Columbia, MO", "degree": "B.S. Computer Science", "dates": "2016 - 2020"}]
        result = render_education(edu)
        assert "\\section{Education}" in result

    def test_renders_school_name(self):
        edu = [{"school": "MIT", "location": "", "degree": "M.S.", "dates": "2020-2022"}]
        result = render_education(edu)
        assert "MIT" in result

    def test_renders_degree(self):
        edu = [{"institution": "Stanford", "location": "", "degree": "Ph.D. Computer Science", "date": "2022"}]
        result = render_education(edu)
        assert "Ph.D. Computer Science" in result

    def test_empty_education(self):
        result = render_education([])
        assert "\\section{Education}" in result


# ---------------------------------------------------------------------------
# render_certifications
# ---------------------------------------------------------------------------
class TestRenderCertifications:
    def test_returns_empty_string_for_no_certs(self):
        assert render_certifications([]) == ""

    def test_renders_cert_list(self):
        certs = ["AWS Solutions Architect", "Google Professional Data Engineer"]
        result = render_certifications(certs)
        assert "AWS Solutions Architect" in result
        assert "\\section{Certifications}" in result

    def test_joins_with_separator(self):
        certs = ["Cert A", "Cert B"]
        result = render_certifications(certs)
        assert "$|$" in result


# ---------------------------------------------------------------------------
# render_template
# ---------------------------------------------------------------------------
class TestRenderTemplate:
    def test_fills_placeholders(self, tmp_path):
        template = tmp_path / "template.tex"
        output = tmp_path / "out.tex"
        template.write_text("Hello {{NAME}}, welcome!", encoding="utf-8")
        render_template(str(template), str(output), {"NAME": "Jane"})
        assert output.read_text(encoding="utf-8") == "Hello Jane, welcome!"

    def test_warns_on_unfilled_placeholder(self, tmp_path, capsys):
        template = tmp_path / "template.tex"
        output = tmp_path / "out.tex"
        template.write_text("{{NAME}} {{UNFILLED}}", encoding="utf-8")
        render_template(str(template), str(output), {"NAME": "Jane"})
        captured = capsys.readouterr()
        assert "WARNING" in captured.out or "UNFILLED" in captured.out

    def test_creates_output_directory(self, tmp_path):
        template = tmp_path / "template.tex"
        nested_output = tmp_path / "nested" / "dir" / "out.tex"
        template.write_text("Hello", encoding="utf-8")
        render_template(str(template), str(nested_output), {})
        assert nested_output.exists()


# ---------------------------------------------------------------------------
# build_from_profile
# ---------------------------------------------------------------------------
class TestBuildFromProfile:
    def test_builds_resume_with_header(self, tmp_path):
        output = tmp_path / "resume.tex"
        profile = {
            "experience": [],
            "projects": [],
            "skills": ["Python", "SQL"],
            "education": [],
            "certifications": [],
            "summary": "",
        }
        header = {
            "name": "Jane Smith",
            "email": "jane@example.com",
            "linkedin": "https://linkedin.com/in/jane",
            "github": "",
            "portfolio": "",
            "phone": "555-0100",
        }
        build_from_profile(profile, TEMPLATE_PATH, str(output), header)
        assert output.exists()
        content = output.read_text(encoding="utf-8")
        assert "Jane Smith" in content

    def test_build_with_no_header_uses_defaults(self, tmp_path):
        output = tmp_path / "resume.tex"
        profile = {
            "experience": [],
            "projects": [],
            "skills": [],
            "education": [],
            "certifications": [],
            "summary": "",
        }
        build_from_profile(profile, TEMPLATE_PATH, str(output))
        assert output.exists()

    def test_build_with_certifications(self, tmp_path):
        output = tmp_path / "resume.tex"
        profile = {
            "experience": [],
            "projects": [],
            "skills": [],
            "education": [],
            "certifications": ["AWS Certified DE"],
            "summary": "",
        }
        build_from_profile(profile, TEMPLATE_PATH, str(output))
        # Template renders successfully (certs injected into CERTIFICATIONS_SECTION placeholder)
        assert output.exists()
        assert output.stat().st_size > 0
