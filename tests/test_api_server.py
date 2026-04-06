"""Tests for api_server.py FastAPI TRACER endpoints."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "skills" / "tailor-resume" / "scripts"))

from api_server import app  # noqa: E402

client = TestClient(app)
HEADERS = {"X-API-Key": "dev-key"}

_JD = "Senior Data Engineer. Spark, Kafka, Airflow, Delta Lake, CI/CD, schema drift."
_BLOB = (
    "Company: Acme Corp\nTitle: Data Engineer\nDates: Jan 2022 - Present\n"
    "- Reduced ETL 73% via CDC upserts, saving $3k/month."
)


def test_health_check():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "2.0.0"


def test_index_returns_html():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_generate_happy_path():
    payload = {
        "jd_text": _JD,
        "artifact_text": _BLOB,
        "artifact_format": "blob",
        "name": "Jane Smith",
        "email": "jane@example.com",
    }
    resp = client.post("/generate", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "ats_score" in data
    assert isinstance(data["ats_score"], int)
    assert 0 <= data["ats_score"] <= 100
    assert "resume_path" in data
    assert data["resume_path"].endswith(".tex")
    assert "gap_summary" in data
    assert isinstance(data["gap_summary"], list)
    assert "vault_version" in data  # None when no token, key must exist


def test_generate_missing_jd_returns_422():
    payload = {"artifact_text": _BLOB, "artifact_format": "blob"}
    resp = client.post("/generate", json=payload, headers=HEADERS)
    assert resp.status_code == 422


def test_generate_bad_api_key_returns_401():
    payload = {"jd_text": _JD, "artifact_text": _BLOB, "artifact_format": "blob"}
    resp = client.post("/generate", json=payload, headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 401


def test_generate_no_api_key_returns_401():
    payload = {"jd_text": _JD, "artifact_text": _BLOB, "artifact_format": "blob"}
    resp = client.post("/generate", json=payload)
    assert resp.status_code == 401


def test_score_happy_path():
    payload = {
        "jd_text": _JD,
        "resume_text": "Experience with Spark, Kafka, Airflow pipelines. Reduced ETL 73%.",
    }
    resp = client.post("/score", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "ats_score" in data
    assert 0 <= data["ats_score"] <= 100
    assert "gap_report" in data
    assert "ats_score_estimate" in data["gap_report"]


def test_score_missing_jd_returns_422():
    resp = client.post("/score", json={"resume_text": "text"}, headers=HEADERS)
    assert resp.status_code == 422


def test_score_missing_resume_returns_422():
    resp = client.post("/score", json={"jd_text": _JD}, headers=HEADERS)
    assert resp.status_code == 422


def test_score_bad_api_key_returns_401():
    payload = {"jd_text": _JD, "resume_text": "Spark Kafka Airflow"}
    resp = client.post("/score", json=payload, headers={"X-API-Key": "bad"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /cover-letter
# ---------------------------------------------------------------------------


def test_cover_letter_happy_path():
    payload = {
        "jd_text": _JD,
        "artifact_text": _BLOB,
        "artifact_format": "blob",
        "name": "Jane Smith",
        "email": "jane@example.com",
        "method": "template",
    }
    resp = client.post("/cover-letter", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "txt" in data
    assert isinstance(data["txt"], str)
    assert len(data["txt"]) > 10
    assert "word_count" in data
    assert isinstance(data["word_count"], int)
    assert "method_used" in data


def test_cover_letter_missing_jd_returns_422():
    resp = client.post("/cover-letter", json={"artifact_text": _BLOB}, headers=HEADERS)
    assert resp.status_code == 422


def test_cover_letter_bad_api_key_returns_401():
    payload = {"jd_text": _JD, "artifact_text": _BLOB}
    resp = client.post("/cover-letter", json=payload, headers={"X-API-Key": "nope"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /ingest/github
# ---------------------------------------------------------------------------


def test_ingest_github_happy_path():
    from unittest.mock import patch
    fake_projects = [
        {"name": "autoapply-ai", "description": "AI job tool", "bullets": [], "tools": ["Python"],
         "url": "https://github.com/n/autoapply-ai", "stars": 42, "source": "github"}
    ]
    with patch("api_server.fetch_user_repos", return_value=fake_projects):
        resp = client.post(
            "/ingest/github",
            json={"username": "narendranathe", "limit": 5},
            headers=HEADERS,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["projects"][0]["name"] == "autoapply-ai"


def test_ingest_github_missing_username_returns_422():
    resp = client.post("/ingest/github", json={"username": ""}, headers=HEADERS)
    assert resp.status_code == 422


def test_ingest_github_bad_api_key_returns_401():
    resp = client.post(
        "/ingest/github",
        json={"username": "someone"},
        headers={"X-API-Key": "bad"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /compare
# ---------------------------------------------------------------------------


def test_compare_happy_path():
    payload = {"jd_text": _JD, "resume_text": "Spark Kafka Airflow pipelines. Reduced ETL 73%."}
    resp = client.post("/compare", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "formula" in data
    assert "claude" in data
    assert 0 <= data["formula"]["score"] <= 100
    assert 0 <= data["claude"]["score"] <= 100
    assert data["formula"]["method_used"] == "formula"
    assert isinstance(data["formula"]["recommendations"], list)
    assert isinstance(data["claude"]["recommendations"], list)


def test_compare_missing_jd_returns_422():
    resp = client.post("/compare", json={"resume_text": "Spark"}, headers=HEADERS)
    assert resp.status_code == 422


def test_compare_bad_api_key_returns_401():
    payload = {"jd_text": _JD, "resume_text": "Spark Kafka"}
    resp = client.post("/compare", json=payload, headers={"X-API-Key": "bad"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# _compile_pdf helper + /generate pdf_path
# ---------------------------------------------------------------------------


def test_generate_pdf_path_null_when_pdflatex_absent():
    """When pdflatex is not on PATH, pdf_path and compile_warning are both null."""
    from unittest.mock import patch
    payload = {
        "jd_text": _JD,
        "artifact_text": _BLOB,
        "artifact_format": "blob",
        "name": "Jane Smith",
        "email": "jane@example.com",
    }
    with patch("api_server.shutil.which", return_value=None):
        resp = client.post("/generate", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "pdf_path" in data
    assert data["pdf_path"] is None
    assert data["compile_warning"] is None


def test_generate_pdf_path_returned_on_success():
    """When pdflatex succeeds, pdf_path ends with .pdf."""
    from pathlib import Path
    from unittest.mock import MagicMock, patch
    payload = {
        "jd_text": _JD,
        "artifact_text": _BLOB,
        "artifact_format": "blob",
    }
    mock_proc = MagicMock()
    mock_proc.returncode = 0

    def fake_which(cmd):
        return "/usr/bin/pdflatex" if cmd == "pdflatex" else None

    def fake_run(args, **kwargs):
        # Create a fake .pdf file next to the .tex
        tex = args[-1]
        pdf = tex.replace(".tex", ".pdf")
        Path(pdf).write_text("fake pdf content")
        return mock_proc

    with patch("api_server.shutil.which", side_effect=fake_which):
        with patch("api_server.subprocess.run", side_effect=fake_run):
            resp = client.post("/generate", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["pdf_path"] is not None
    assert data["pdf_path"].endswith(".pdf")
    assert data["compile_warning"] is None


def test_generate_compile_warning_on_pdflatex_failure():
    """When pdflatex exits non-zero, pdf_path is null and compile_warning is set."""
    from unittest.mock import MagicMock, patch
    payload = {"jd_text": _JD, "artifact_text": _BLOB, "artifact_format": "blob"}
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = b"LaTeX error: undefined control sequence"

    with patch("api_server.shutil.which", return_value="/usr/bin/pdflatex"):
        with patch("api_server.subprocess.run", return_value=mock_proc):
            resp = client.post("/generate", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["pdf_path"] is None
    assert data["compile_warning"] is not None
    assert "pdflatex exit 1" in data["compile_warning"]


def test_generate_compile_pdf_false_skips_compilation():
    """compile_pdf=False skips pdflatex even if it would be available."""
    from unittest.mock import patch
    payload = {
        "jd_text": _JD,
        "artifact_text": _BLOB,
        "artifact_format": "blob",
        "compile_pdf": False,
    }
    with patch("api_server.subprocess.run") as mock_run:
        resp = client.post("/generate", json=payload, headers=HEADERS)
    mock_run.assert_not_called()
    data = resp.json()
    assert data["pdf_path"] is None


# ---------------------------------------------------------------------------
# /cover-letter pdf_path
# ---------------------------------------------------------------------------


def test_cover_letter_pdf_path_null_when_pdflatex_absent():
    from unittest.mock import patch
    payload = {
        "jd_text": _JD,
        "artifact_text": _BLOB,
        "artifact_format": "blob",
        "method": "template",
    }
    with patch("api_server.shutil.which", return_value=None):
        resp = client.post("/cover-letter", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "pdf_path" in data
    assert data["pdf_path"] is None


def test_cover_letter_pdf_path_returned_on_success():
    from pathlib import Path
    from unittest.mock import MagicMock, patch
    payload = {
        "jd_text": _JD,
        "artifact_text": _BLOB,
        "artifact_format": "blob",
        "method": "template",
    }
    mock_proc = MagicMock()
    mock_proc.returncode = 0

    def fake_run(args, **kwargs):
        tex = args[-1]
        pdf = tex.replace(".tex", ".pdf")
        Path(pdf).write_text("fake pdf content")
        return mock_proc

    with patch("api_server.shutil.which", return_value="/usr/bin/pdflatex"):
        with patch("api_server.subprocess.run", side_effect=fake_run):
            resp = client.post("/cover-letter", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["pdf_path"] is not None
    assert data["pdf_path"].endswith(".pdf")
