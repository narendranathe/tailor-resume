"""
_make_pdf.py
Generate the canonical sample.pdf fixture for parser integration tests.

Run from repo root:
    python tests/fixtures/parsers/_make_pdf.py

Uses reportlab (a dev-only dep). The resulting PDF is single-column,
plain-text, and decodable by pdfminer.six / pypdf / the stdlib extractor.
"""
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer


HERE = Path(__file__).parent
OUT = HERE / "sample.pdf"


def build():
    styles = getSampleStyleSheet()
    name_style = ParagraphStyle(
        "Name", parent=styles["Title"], fontSize=18, spaceAfter=4, alignment=1
    )
    contact_style = ParagraphStyle(
        "Contact", parent=styles["Normal"], fontSize=10, alignment=1, spaceAfter=12
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontSize=13,
        spaceBefore=10,
        spaceAfter=4,
    )
    role_style = ParagraphStyle(
        "Role", parent=styles["Normal"], fontSize=11, spaceAfter=2
    )
    bullet_style = ParagraphStyle(
        "Bullet",
        parent=styles["Normal"],
        fontSize=10,
        leftIndent=14,
        bulletIndent=2,
        spaceAfter=2,
    )

    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=letter,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )
    flow = []

    flow.append(Paragraph("JANE DOE", name_style))
    flow.append(
        Paragraph(
            "jane.doe@example.com &nbsp;|&nbsp; 555-123-4567 &nbsp;|&nbsp; "
            "linkedin.com/in/janedoe &nbsp;|&nbsp; Dallas, TX",
            contact_style,
        )
    )

    # Experience
    flow.append(Paragraph("PROFESSIONAL EXPERIENCE", section_style))

    flow.append(
        Paragraph(
            "<b>Senior Data Engineer, DataWorks Inc</b> &nbsp;&nbsp; "
            "March 2022 &ndash; Present",
            role_style,
        )
    )
    for b in (
        "Built a governed semantic layer on Azure Databricks with Delta Lake, "
        "defining 40+ KPI metrics across Finance, ML, and BI teams; cut metric "
        "discrepancies from 12 weekly incidents to zero",
        "Owned CI/CD end-to-end through Azure DevOps for 15 data pipelines, "
        "compressing deployment cycles from 8 weeks to 6 days",
        "Reengineered ETL from full-table reloads to CDC incremental merge upserts "
        "on Delta Lake, cutting batch runtime from 45 min to 9 min and compute costs by 68%",
        "Migrated Spark jobs to AKS with HPA, consolidating 18 nodes to 4-8 dynamic, "
        "reducing monthly cloud spend by $4,100",
    ):
        flow.append(Paragraph("&bull; " + b, bullet_style))

    flow.append(Spacer(1, 4))
    flow.append(
        Paragraph(
            "<b>Data Engineer, Acme Analytics Corp</b> &nbsp;&nbsp; "
            "August 2019 &ndash; February 2022",
            role_style,
        )
    )
    for b in (
        "Engineered Azure AI Anomaly Detector pipelines achieving 95%+ accuracy "
        "across 200+ monitored metrics",
        "Built Elasticsearch enterprise search indexing 150K+ internal documents, "
        "reducing support desk volume by 75%",
        "Developed Python ETL framework with Pytest unit tests and GitHub Actions CI, "
        "reducing production data defects by 40% year-over-year",
    ):
        flow.append(Paragraph("&bull; " + b, bullet_style))

    # Education
    flow.append(Paragraph("EDUCATION", section_style))
    flow.append(
        Paragraph(
            "University of Missouri-Columbia, Columbia, MO", role_style
        )
    )
    flow.append(
        Paragraph(
            "Master of Science in Computer Science &nbsp;&nbsp; "
            "August 2017 &ndash; May 2019",
            role_style,
        )
    )

    # Skills
    flow.append(Paragraph("SKILLS", section_style))
    flow.append(Paragraph("Languages: Python, SQL, Bash, Java, Scala", role_style))
    flow.append(Paragraph("Data: Spark, Kafka, Airflow, dbt, Delta Lake", role_style))
    flow.append(Paragraph("Cloud: Azure, AWS, Databricks", role_style))
    flow.append(Paragraph("DevOps: Docker, Kubernetes, Terraform, CI/CD", role_style))

    # Certifications
    flow.append(Paragraph("CERTIFICATIONS", section_style))
    flow.append(
        Paragraph(
            "&bull; AWS Certified Solutions Architect &mdash; Associate",
            bullet_style,
        )
    )
    flow.append(
        Paragraph(
            "&bull; Databricks Certified Data Engineer Professional",
            bullet_style,
        )
    )

    doc.build(flow)
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    build()
