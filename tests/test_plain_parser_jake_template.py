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

from parsers.plain_parser import _DATE_PATTERN, _parse_plain_resume_text


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
        assert r.start == "July 2024"
        assert r.end == "Present"
        assert len(r.bullets) == 2

    def test_second_role_fields(self, profile):
        r = profile.experience[1]
        assert r.title == "Data Engineer"
        assert "Missouri" in r.company
        assert r.location == "Rolla, MO"
        # #102 — start date must be the full 'Aug. 2023', not blank
        assert r.start.startswith("Aug")
        assert r.end == "July 2024"
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
