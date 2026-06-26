"""
Regression tests for Jake-LaTeX-template resume parsing (issues #101 #102 #103 #104).

These fixtures capture two flavors of pdf-extracted text from the same physical
Jake-template resume:

  - Fixture A: pypdf-style ordered text (reading order matches visual flow).
  - Fixture B: pdfminer-style column-ordered text (dates pool at the top of the
    page because pdfminer reads by visual column).

The bugs being regressed:
  #101 — Candidate name above 'Experience' header was parsed as a role title.
  #102 — When a line is a pure date range (or starts with 'Aug. 2023 – July
        2024'), the parser took the next line as the company and produced a
        role with an empty/garbage title.
  #103 — Project parser used bullet lines as project names (any '•'-prefixed
        line was treated as a project header).
  #104 — Bullets fell through with no current_role and were silently dropped.
"""
from __future__ import annotations

import pytest

from parsers.plain_parser import (
    _DATE_PATTERN,
    _detect_section,
    _parse_education_oneliner,
    _parse_plain_resume_text,
)


# ---------------------------------------------------------------------------
# Fixtures — real text extracted from Naren_citi.pdf
# ---------------------------------------------------------------------------

FIXTURE_A_PYPDF = """\
Narendranath Edara
+1 (573) 466-6656 | edara.narendranath@gmail.com | linkedin.com/in/narendranathe | narendranathe.github.io
Experience
Data Engineer July 2024 – Present
ExponentHR Dallas, TX
• Reengineered CDC-based ETL to incremental capture with idempotent merge upserts, partition-aware writes, and
schema-versioned data contracts, cutting batch runtime from ~30 min to under 8 min and compute costs by ~67%
• Architected governed semantic layer on Microsoft Fabric serving 400+ enterprise clients across payroll, benefits, and
expenses domains, cutting query latency from 12s to under 4s through SQL tuning and indexing
Data Engineer Aug. 2023 – July 2024
Missouri S&T Rolla, MO
• Engineered anomaly detection pipelines with tunable thresholds per service, achieving 95%+ accuracy on
time-series profiles, filtering ~250 weekly non-actionable alerts (signal-to-noise from 1:5 to 1:1.2)
• Migrated from static VMs to AKS with HPA, raising CPU utilization 12% to 64%, consolidating 20 nodes to 4 to 8
Projects
Real-Time Fraud Detection Pipeline | PySpark, Kafka, Airflow, MLflow, Docker, Prometheus 2026
• Built event-driven streaming pipeline serving 100+ TPS with sub-ms latency using Kafka for CDC-style ingestion
and containerized endpoints with MLflow tracking
• Implemented end-to-end observability (Prometheus + Grafana) with Airflow-orchestrated batch and streaming
workflows in Dockerized infrastructure
JobScout – Automated Data Integration Platform | Python, FastAPI, SQLite, GitHub Actions 2025
• Built Python automation framework ingesting 109 data sources with validation, reconciliation, error handling, and
circuit breakers isolating failing integrations without pipeline downtime
Education
Missouri University of Science and Technology Rolla, MO
Master of Science in Information Science and Technology; GPA: 4.0/4.0 Jan. 2022 – Dec. 2023
"""


FIXTURE_B_PDFMINER = """\
Narendranath Edara
July 2024 – Present
Aug. 2023 – July 2024
Rolla, MO
+1 (573) 466-6656 | edara.narendranath@gmail.com | linkedin.com/in/narendranathe | narendranathe.github.io
Experience
Data Engineer
ExponentHR
Dallas, TX
• Reengineered CDC-based ETL to incremental capture with idempotent merge upserts
• Architected governed semantic layer on Microsoft Fabric serving 400+ enterprise clients
Data Engineer
Missouri S&T
• Engineered anomaly detection pipelines with tunable thresholds per service
• Migrated from static VMs to AKS with HPA, raising CPU utilization 12% to 64%
Projects
2026
• Built event-driven streaming pipeline serving 100+ TPS with sub-ms latency using Kafka
Real-Time Fraud Detection Pipeline | PySpark, Kafka, Airflow, MLflow, Docker, Prometheus
• Implemented end-to-end observability (Prometheus + Grafana) with Airflow-orchestrated batch
2025
JobScout – Automated Data Integration Platform | Python, FastAPI, SQLite, GitHub Actions
• Built Python automation framework ingesting 109 data sources
"""


# ---------------------------------------------------------------------------
# Date regex — #102 first-match correctness
# ---------------------------------------------------------------------------

class TestDatePatternFirstMatch:
    """Regression for #102: 'Aug. 2023 – July 2024' should match in full."""

    def test_full_range_with_period_after_month(self):
        m = _DATE_PATTERN.search("Aug. 2023 – July 2024")
        assert m is not None
        assert m.group(0).strip() == "Aug. 2023 – July 2024"

    def test_full_range_no_period(self):
        m = _DATE_PATTERN.search("Aug 2023 – July 2024")
        assert m is not None
        assert m.group(0).strip() == "Aug 2023 – July 2024"

    def test_range_with_present(self):
        m = _DATE_PATTERN.search("July 2024 – Present")
        assert m is not None
        assert m.group(0).strip() == "July 2024 – Present"

    def test_embedded_in_title_line(self):
        """The match must be the FULL range, not just the start date."""
        m = _DATE_PATTERN.search("Data Engineer Aug. 2023 – July 2024")
        assert m is not None
        assert "Aug" in m.group(0) and "July 2024" in m.group(0)

    # Fix 5 — "to" separator (LinkedIn / DOCX exports)
    def test_range_with_to_separator(self):
        m = _DATE_PATTERN.search("Jan 2021 to Dec 2022")
        assert m is not None, "'Jan 2021 to Dec 2022' should match"
        assert "Jan 2021" in m.group(0) and "Dec 2022" in m.group(0)

    def test_range_with_thru_separator(self):
        m = _DATE_PATTERN.search("Jan 2021 thru Dec 2022")
        assert m is not None, "'Jan 2021 thru Dec 2022' should match"

    def test_year_range_with_to(self):
        m = _DATE_PATTERN.search("2019 to 2022")
        assert m is not None, "'2019 to 2022' should match"


# ---------------------------------------------------------------------------
# Fix 6 — Section header alias coverage
# ---------------------------------------------------------------------------

class TestSectionHeaders:
    """Regression for Fix 6: extended aliases map to canonical section names."""

    def test_employment_history(self):
        assert _detect_section("Employment History") == "experience"

    def test_work_experience(self):
        assert _detect_section("Work Experience") == "experience"

    def test_professional_experience(self):
        assert _detect_section("Professional Experience") == "experience"

    def test_technical_projects(self):
        assert _detect_section("Technical Projects") == "projects"

    def test_side_projects(self):
        assert _detect_section("Side Projects") == "projects"

    def test_open_source(self):
        assert _detect_section("Open Source") == "projects"

    def test_achievements(self):
        assert _detect_section("Achievements") == "certifications"

    def test_honors(self):
        assert _detect_section("Honors") == "certifications"

    def test_awards(self):
        assert _detect_section("Awards") == "certifications"


# ---------------------------------------------------------------------------
# Fixture A — ordered-text path (the easier case)
# ---------------------------------------------------------------------------

class TestFixtureAOrderedText:
    @pytest.fixture
    def profile(self):
        return _parse_plain_resume_text(FIXTURE_A_PYPDF)

    def test_two_experience_roles(self, profile):
        assert len(profile.experience) == 2, (
            f"expected 2 roles, got {len(profile.experience)}: "
            f"{[r.title for r in profile.experience]}"
        )

    def test_first_role_is_not_candidate_name(self, profile):
        # #101 — name should not become a role title
        for r in profile.experience:
            assert "Narendranath" not in r.title, (
                f"candidate name leaked into role title: {r.title!r}"
            )

    def test_first_role_fields(self, profile):
        r = profile.experience[0]
        assert r.title == "Data Engineer"
        assert r.company == "ExponentHR"
        assert r.location == "Dallas, TX"
        # FIX 4: dates are normalized to abbreviated month + year
        assert r.start == "Jul 2024"
        assert r.end == "Present"
        assert len(r.bullets) == 2

    def test_second_role_fields(self, profile):
        r = profile.experience[1]
        assert r.title == "Data Engineer"
        assert "Missouri" in r.company
        assert r.location == "Rolla, MO"
        # #102 — start date must not be blank; FIX 4 normalizes to "Aug 2023"
        assert r.start.startswith("Aug")
        # FIX 4: dates are normalized to abbreviated month + year
        assert r.end == "Jul 2024"
        assert len(r.bullets) == 2

    def test_two_projects(self, profile):
        assert len(profile.projects) == 2, (
            f"expected 2 projects, got {len(profile.projects)}: "
            f"{[p.name for p in profile.projects]}"
        )

    def test_first_project_header_parsed(self, profile):
        p = profile.projects[0]
        # #103 — name must be project header, not bullet text
        assert p.name == "Real-Time Fraud Detection Pipeline"
        assert "PySpark" in p.tech or "PySpark" in (",".join(p.tech))
        assert len(p.bullets) == 2

    def test_second_project_header_parsed(self, profile):
        p = profile.projects[1]
        assert p.name.startswith("JobScout"), f"got {p.name!r}"

    def test_no_role_content_in_projects(self, profile):
        for p in profile.projects:
            assert "ExponentHR" not in p.name
            assert "Missouri" not in p.name
            assert not p.name.startswith("Data Engineer")


# ---------------------------------------------------------------------------
# Fixture B — pdfminer column-disordered text (the harder case)
# ---------------------------------------------------------------------------

class TestFixtureBDisorderedText:
    """
    For B we relax to invariants: no name-as-title, no date-as-title, no
    bullet-as-project-name, every role has at least one bullet.
    """

    @pytest.fixture
    def profile(self):
        return _parse_plain_resume_text(FIXTURE_B_PDFMINER)

    def test_at_least_two_experience_roles(self, profile):
        assert len(profile.experience) >= 2, (
            f"expected >=2 roles, got {len(profile.experience)}: "
            f"{[(r.title, r.company) for r in profile.experience]}"
        )

    def test_no_role_title_is_candidate_name(self, profile):
        for r in profile.experience:
            assert "Narendranath" not in r.title, (
                f"candidate name leaked into role title: {r.title!r}"
            )

    def test_no_role_title_is_pure_date(self, profile):
        for r in profile.experience:
            m = _DATE_PATTERN.search(r.title)
            # If the title contains a date as its primary content, bug #102
            # has resurfaced.  Allow titles with no date at all.
            assert m is None or len(r.title.replace(m.group(0), "").strip()) > 3, (
                f"role title is essentially a date: {r.title!r}"
            )

    def test_each_role_has_bullet(self, profile):
        for r in profile.experience:
            assert len(r.bullets) >= 1, (
                f"role {r.title!r}/{r.company!r} has no bullets (bug #104)"
            )

    def test_at_least_two_projects(self, profile):
        assert len(profile.projects) >= 2, (
            f"expected >=2 projects, got {len(profile.projects)}: "
            f"{[p.name for p in profile.projects]}"
        )

    def test_fraud_pipeline_project_recognised(self, profile):
        names = [p.name for p in profile.projects]
        assert any("Real-Time Fraud Detection Pipeline" == n for n in names), (
            f"expected fraud-pipeline project, got {names}"
        )

    def test_no_bullet_text_as_project_name(self, profile):
        for p in profile.projects:
            assert not p.name.startswith("Built "), (
                f"bullet text used as project name: {p.name!r}"
            )
            assert not p.name.startswith("Implemented "), (
                f"bullet text used as project name: {p.name!r}"
            )

    def test_fraud_pipeline_has_two_bullets(self, profile):
        """Regression for #115: orphaned bullet appearing before the project
        header in column-ordered pdfminer output must be attached to the
        correct project, not dropped."""
        fraud = next(
            (p for p in profile.projects if p.name == "Real-Time Fraud Detection Pipeline"),
            None,
        )
        assert fraud is not None, "fraud pipeline project not found"
        assert len(fraud.bullets) >= 2, (
            f"expected ≥2 bullets for fraud pipeline project (bug #115), "
            f"got {len(fraud.bullets)}: {[b.text[:60] for b in fraud.bullets]}"
        )


# ---------------------------------------------------------------------------
# Education single-line parser (Issue #129)
# ---------------------------------------------------------------------------

class TestParseEducationOneliner:
    """Unit tests for _parse_education_oneliner (Issue #129).

    Validates that condensed one-liner education lines — common in LinkedIn
    exports and DOCX templates — are parsed into full institution/degree/dates
    dicts rather than silently losing GPA or date fields.
    """

    def test_pipe_dash_gpa_dates(self):
        line = "Missouri S&T — M.S. Information Science | GPA: 4.0 | Jan 2022 – Dec 2023"
        result = _parse_education_oneliner(line)
        assert result is not None, "one-liner should match"
        assert "Missouri S&T" in result["institution"]
        assert "M.S. Information Science" in result["degree"]
        assert "GPA: 4.0" in result["degree"]
        assert "Jan 2022" in result["dates"] or "Dec 2023" in result["dates"]

    def test_pipe_separator_no_gpa(self):
        line = "University of Texas | B.S. Computer Science | 2018 – 2022"
        result = _parse_education_oneliner(line)
        assert result is not None
        assert "University of Texas" in result["institution"]
        assert "B.S. Computer Science" in result["degree"]
        assert "2018" in result["dates"] or "2022" in result["dates"]

    def test_no_dates_returns_empty_dates(self):
        line = "MIT — Ph.D. Machine Learning"
        result = _parse_education_oneliner(line)
        assert result is not None
        assert "MIT" in result["institution"]
        assert "Ph.D. Machine Learning" in result["degree"]
        assert result["dates"] == ""

    def test_bare_date_line_returns_none(self):
        """A bare date range must NOT match — it should fall through to existing parser."""
        line = "Jan 2022 – Dec 2023"
        result = _parse_education_oneliner(line)
        assert result is None

    def test_doublespace_separated(self):
        line = "University of Michigan  B.S. Computer Science  2015 – 2019"
        result = _parse_education_oneliner(line)
        assert result is not None
        assert "University of Michigan" in result["institution"]
        assert "B.S." in result["degree"]

    def test_existing_multiline_education_unchanged(self):
        """Jake-template multi-line education must still parse correctly (regression)."""
        text = """\
Education
Missouri University of Science and Technology Rolla, MO
Master of Science in Information Science and Technology; GPA: 4.0/4.0 Jan. 2022 – Dec. 2023
"""
        profile = _parse_plain_resume_text(text)
        assert profile.education, "education list must not be empty"
        edu = profile.education[0]
        assert "Missouri University" in edu["institution"] or "Missouri University" in edu.get("institution", "")

    def test_location_field_empty(self):
        """Parsed one-liners never invent a location — that field stays empty."""
        line = "Stanford University — M.S. Computer Science | 2020 – 2022"
        result = _parse_education_oneliner(line)
        assert result is not None
        assert result["location"] == ""

    def test_gpa_with_denominator(self):
        """GPA in X.X/4.0 format must preserve the slash-denominator in the degree string."""
        line = "MIT | Ph.D. CS | GPA: 3.9/4.0 | 2015 – 2020"
        result = _parse_education_oneliner(line)
        assert result is not None
        assert result["institution"] == "MIT"
        # The full fraction must appear in the degree string, not just '3.9'
        assert "3.9/4.0" in result["degree"], (
            f"GPA denominator '/4.0' was silently dropped; degree={result['degree']!r}"
        )
        assert "2015" in result["dates"] or "2020" in result["dates"]

    def test_cgpa_not_munged_by_gpa_re_substring_match(self):
        """'CGPA: 8.9/10' must not leave a garbage 'C' fragment as the degree."""
        line = "IIT Bombay | B.Tech Computer Science | 2010 – 2014 | CGPA: 8.9/10"
        result = _parse_education_oneliner(line)
        assert result is not None
        assert "IIT Bombay" in result["institution"]
        assert "B.Tech" in result["degree"]
        # Degree must not start with a bare 'C' from the CGPA substring match
        assert not result["degree"].startswith("C "), (
            f"CGPA substring match left garbage in degree: {result['degree']!r}"
        )
        # GPA value must appear in degree
        assert "8.9" in result["degree"], (
            f"CGPA value lost from degree: {result['degree']!r}"
        )

    def test_degree_first_format_pipe(self):
        """When the degree appears before the institution in a pipe-delimited line,
        the parser must detect and swap them rather than storing the degree as institution."""
        line = "M.S. Computer Science | Stanford University | 2020 – 2022"
        result = _parse_education_oneliner(line)
        assert result is not None
        # With the degree-first swap, institution must be Stanford, not 'M.S. Computer Science'
        assert "Stanford" in result["institution"], (
            f"Degree-first swap failed; institution={result['institution']!r}"
        )
        assert "M.S." in result["degree"], (
            f"Degree not captured after swap; degree={result['degree']!r}"
        )
        assert "2020" in result["dates"] or "2022" in result["dates"]

    def test_year_first_format_doublespace(self):
        """Year-first moderncv format must parse correctly; the digit guard must not
        block lines that have a date prefix followed by substantive content."""
        line = "2014–2018  B.Sc. Mathematics  University of Edinburgh"
        result = _parse_education_oneliner(line)
        assert result is not None, (
            "Year-first line was rejected by the digit guard (Strategy 0 missing)"
        )
        assert "Edinburgh" in result["institution"] or "University" in result["institution"], (
            f"Institution not extracted; institution={result['institution']!r}"
        )
        assert "B.Sc." in result["degree"] or "Mathematics" in result["degree"]
        assert "2014" in result["dates"] or "2018" in result["dates"]

    def test_september_full_word_rejected_as_bare_date(self):
        """A line starting with 'September YYYY' must be treated as a bare date line
        and return None, not parsed as an institution."""
        line = "September 2022 – May 2023"
        result = _parse_education_oneliner(line)
        assert result is None, (
            f"'September YYYY' bare date line was incorrectly parsed: {result!r}"
        )

    def test_may_university_not_rejected_by_month_guard(self):
        """'May University' must NOT be rejected — 'May' here is part of the name,
        not a month-only date prefix."""
        line = "May University | M.S. CS | 2020 – 2022"
        result = _parse_education_oneliner(line)
        # The refined guard checks for a digit immediately after the month word.
        # 'May University' has no digit after 'May', so it should pass.
        assert result is not None, (
            "'May University' was wrongly rejected by the month-name guard"
        )
        assert "University" in result["institution"]

    def test_comma_separated_institution_first(self):
        """Comma-delimited format with institution first must parse via Strategy 3."""
        line = "Stanford University, B.S. CS, 2018 – 2022"
        result = _parse_education_oneliner(line)
        assert result is not None, (
            "Comma-separated format fell through Strategy 3 and returned None"
        )
        assert "Stanford" in result["institution"]
        assert "B.S." in result["degree"]
        assert "2018" in result["dates"] or "2022" in result["dates"]

    def test_dates_does_not_contain_trailing_junk(self):
        """When the date field is followed by an additional pipe-separated fragment,
        that fragment must not appear inside the dates string."""
        line = "Stanford | B.S. CS | 2020 – 2022 | Honors Program"
        result = _parse_education_oneliner(line)
        assert result is not None
        # Dates must contain only the year range, not 'Honors Program'
        assert "Honors" not in result["dates"], (
            f"Trailing junk in dates field: {result['dates']!r}"
        )
        assert "2020" in result["dates"] or "2022" in result["dates"]

    def test_doublespace_three_tokens_no_pipe_in_degree(self):
        """When three double-space-separated tokens are present, the degree field
        must not contain a pipe separator artifact from the internal rejoin."""
        line = "University of California, Berkeley  Bachelor of Science  Computer Science  2016 – 2020"
        result = _parse_education_oneliner(line)
        assert result is not None
        assert "Berkeley" in result["institution"]
        # Degree must not contain ' | ' from the old ' | '.join(raw_parts[1:]) approach
        assert "|" not in result["degree"], (
            f"Pipe artifact in degree field: {result['degree']!r}"
        )
        assert "Bachelor" in result["degree"] or "Science" in result["degree"]
        assert "2016" in result["dates"] or "2020" in result["dates"]

    def test_merge_same_institution_stub_normalized(self):
        """A stub entry (institution only, no degree/dates) followed by a full
        one-liner for the same institution must merge into a single entry.
        Institution equality check must be case/whitespace insensitive."""
        text = """\
Education
MIT
MIT | Ph.D. Machine Learning | 2020 – 2023
"""
        profile = _parse_plain_resume_text(text)
        # The stub 'MIT' and the one-liner 'MIT | ...' must merge, not duplicate.
        assert len(profile.education) == 1, (
            f"Same-institution stub should merge into one entry, got "
            f"{len(profile.education)}: {profile.education}"
        )
        edu = profile.education[0]
        assert "MIT" in edu["institution"]
        assert "Ph.D." in edu["degree"]
        assert "2020" in edu["dates"] or "2023" in edu["dates"]

    def test_integration_multiple_education_entries(self):
        """Two distinct one-liner education entries must both parse and appear
        as separate items in profile.education."""
        text = """\
Education
MIT | Ph.D. Machine Learning | 2020 – 2023
University of Texas | B.S. Computer Science | 2016 – 2020
"""
        profile = _parse_plain_resume_text(text)
        assert len(profile.education) == 2, (
            f"Expected 2 education entries, got {len(profile.education)}: {profile.education}"
        )
        insts = [e["institution"] for e in profile.education]
        assert any("MIT" in i for i in insts), f"MIT not found in {insts}"
        assert any("Texas" in i for i in insts), f"Texas not found in {insts}"
        for edu in profile.education:
            assert edu["degree"], f"Degree empty for {edu['institution']}"
            assert edu["dates"], f"Dates empty for {edu['institution']}"

    def test_false_positive_experience_line_returns_none(self):
        """An experience-section line must not be parsed as education."""
        line = "Data Engineer July 2024 – Present"
        result = _parse_education_oneliner(line)
        assert result is None, (
            f"Experience line incorrectly parsed as education: {result!r}"
        )

    def test_false_positive_skills_line_returns_none(self):
        """A comma-delimited skills line must not fire Strategy 3."""
        line = "Python, TensorFlow, PyTorch, Kafka"
        result = _parse_education_oneliner(line)
        # Strategy 3 requires at least one degree or institution keyword among parts;
        # a plain skills line has neither, so it must return None.
        assert result is None, (
            f"Skills line incorrectly parsed as education: {result!r}"
        )

    def test_false_positive_url_line_returns_none(self):
        """A URL/contact line must not be parsed as education."""
        line = "See https://github.com/user"
        result = _parse_education_oneliner(line)
        assert result is None, (
            f"URL line incorrectly parsed as education: {result!r}"
        )

    def test_doublespace_separated_checks_dates_and_location(self):
        """Strengthens the existing test_doublespace_separated to also assert
        that dates and location are correctly populated."""
        line = "University of Michigan  B.S. Computer Science  2015 – 2019"
        result = _parse_education_oneliner(line)
        assert result is not None
        assert result["institution"] == "University of Michigan"
        assert "B.S. Computer Science" in result["degree"]
        assert "2015" in result["dates"] or "2019" in result["dates"], (
            f"Dates not captured; dates={result['dates']!r}, degree={result['degree']!r}"
        )
        assert result["location"] == ""
        # Degree must not contain a pipe artifact
        assert "|" not in result["degree"]
