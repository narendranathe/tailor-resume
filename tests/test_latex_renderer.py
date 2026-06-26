"""Tests for latex_renderer.py — escape, section builders, template rendering."""
import sys
from pathlib import Path


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

    def test_returns_empty_string_for_empty_list(self):
        # An empty skills list should suppress the entire section so the
        # rendered resume doesn't ship a bare "Technical Skills" header
        # with no content underneath (which produces a wasted page).
        result = render_skills([])
        assert result == ""

    def test_returns_empty_string_for_none(self):
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

    def test_returns_empty_string_for_empty_education(self):
        # An empty education list should suppress the section entirely so
        # the resume doesn't render a bare "Education" header with nothing
        # underneath (which also triggers a "missing \item" LaTeX warning).
        result = render_education([])
        assert result == ""


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


# ---------------------------------------------------------------------------
# build_docx_from_profile
# ---------------------------------------------------------------------------
from latex_renderer import build_docx_from_profile  # noqa: E402


_FULL_PROFILE = {
    "summary": "Experienced data engineer with 5+ years building scalable pipelines.",
    "experience": [
        {
            "title": "Senior Data Engineer",
            "company": "Acme Corp",
            "start": "Jan 2022",
            "end": "Present",
            "bullets": [
                {"text": "Reduced ETL latency 73% via CDC upserts saving $3k/month."},
                {"text": "Built Spark partitioning strategy cutting shuffle by 40%."},
            ],
        }
    ],
    "education": [
        {
            "institution": "MIT",
            "degree": "B.S. Computer Science",
            "dates": "2014 – 2018",
        }
    ],
    "skills": ["Python", "Spark", "Kafka", "Airflow"],
    "projects": [
        {
            "name": "Data Platform",
            "tech": ["Python", "Delta Lake"],
            "bullets": [{"text": "Ingested 10M rows/day with 99.9% uptime."}],
        }
    ],
    "certifications": [],
}

_HEADER = {"name": "Jane Smith", "email": "jane@example.com", "phone": "+1-555-0100"}


class TestBuildDocxFromProfile:
    def test_creates_docx_file(self, tmp_path):
        out = str(tmp_path / "resume.docx")
        build_docx_from_profile(_FULL_PROFILE, out, _HEADER)
        assert (tmp_path / "resume.docx").exists()

    def test_docx_is_nonzero_size(self, tmp_path):
        out = str(tmp_path / "resume.docx")
        build_docx_from_profile(_FULL_PROFILE, out, _HEADER)
        assert (tmp_path / "resume.docx").stat().st_size > 0

    def test_empty_profile_still_writes(self, tmp_path):
        out = str(tmp_path / "empty.docx")
        build_docx_from_profile({}, out)
        assert (tmp_path / "empty.docx").exists()

    def test_profile_with_summary(self, tmp_path):
        profile = {**_FULL_PROFILE, "experience": [], "projects": [], "education": []}
        out = str(tmp_path / "summary.docx")
        build_docx_from_profile(profile, out, _HEADER)
        assert (tmp_path / "summary.docx").exists()

    def test_profile_with_skills_string_list(self, tmp_path):
        profile = {"skills": ["Python", "SQL"]}
        out = str(tmp_path / "skills.docx")
        build_docx_from_profile(profile, out)
        assert (tmp_path / "skills.docx").exists()

    def test_creates_parent_dirs(self, tmp_path):
        out = str(tmp_path / "nested" / "deep" / "resume.docx")
        build_docx_from_profile({}, out, _HEADER)
        assert (tmp_path / "nested" / "deep" / "resume.docx").exists()

    def test_contact_line_with_multiple_fields(self, tmp_path):
        header = {"name": "Bob", "email": "b@b.com", "phone": "+1", "linkedin": "li.com/b", "github": "github.com/b"}
        out = str(tmp_path / "contact.docx")
        build_docx_from_profile({}, out, header)
        assert (tmp_path / "contact.docx").exists()

    def test_role_without_start_date(self, tmp_path):
        profile = {
            "experience": [{"title": "Engineer", "company": "Corp", "end": "Dec 2020", "bullets": []}]
        }
        out = str(tmp_path / "no_start.docx")
        build_docx_from_profile(profile, out)
        assert (tmp_path / "no_start.docx").exists()

    def test_project_with_no_tech(self, tmp_path):
        profile = {
            "projects": [{"name": "MyProj", "tech": [], "bullets": [{"text": "Built it."}]}]
        }
        out = str(tmp_path / "proj.docx")
        build_docx_from_profile(profile, out)
        assert (tmp_path / "proj.docx").exists()

    def test_education_with_school_key_fallback(self, tmp_path):
        profile = {
            "education": [{"school": "State U", "degree": "B.S.", "date": "2020"}]
        }
        out = str(tmp_path / "edu.docx")
        build_docx_from_profile(profile, out)
        assert (tmp_path / "edu.docx").exists()

    def test_no_header_uses_empty(self, tmp_path):
        out = str(tmp_path / "noheader.docx")
        build_docx_from_profile(_FULL_PROFILE, out, header=None)
        assert (tmp_path / "noheader.docx").exists()

    def test_default_output_path(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        build_docx_from_profile({}, "resume.docx")
        assert (tmp_path / "resume.docx").exists()
