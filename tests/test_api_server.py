"""Tests for api_server.py FastAPI TRACER endpoints.

All pipeline-heavy operations (execute_text, run_analysis, build_cover_letter,
fetch_user_repos) are monkeypatched so tests run fast and never call real LLMs,
file I/O, or network services.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List
from unittest.mock import patch

import pytest

# Guard: skip entire module when FastAPI cannot be instantiated (version mismatch)
try:
    from fastapi import FastAPI as _FastAPI
    _FastAPI()
except Exception as _fastapi_err:
    pytest.skip(
        f"FastAPI not usable in this environment: {_fastapi_err}",
        allow_module_level=True,
    )

from fastapi.testclient import TestClient  # noqa: E402

_SCRIPTS = Path(__file__).parent.parent / ".claude" / "skills" / "tailor-resume" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# Guard: skip if api_server itself can't be imported (missing deps, wrong FastAPI version)
try:
    import api_server  # noqa: E402
    from api_server import app  # noqa: E402
except Exception as _import_err:
    pytest.skip(
        f"api_server could not be imported: {_import_err}",
        allow_module_level=True,
    )

client = TestClient(app)
HEADERS = {"X-API-Key": "dev-key"}

_JD = "Senior Data Engineer. Spark, Kafka, Airflow, Delta Lake, CI/CD, schema drift."
_BLOB = (
    "Company: Acme Corp\nTitle: Data Engineer\nDates: Jan 2022 - Present\n"
    "- Reduced ETL 73% via CDC upserts, saving $3k/month."
)


# ---------------------------------------------------------------------------
# Shared fake dataclasses (mirror TailorResult / GapReport)
# ---------------------------------------------------------------------------

@dataclass
class _FakeGapSignal:
    category: str = "tools"
    priority: str = "high"
    jd_keywords: List[str] = field(default_factory=lambda: ["Spark"])
    profile_keywords: List[str] = field(default_factory=list)
    coverage_ratio: float = 0.5
    suggested_angles: List[str] = field(default_factory=lambda: ["Add Spark project"])


@dataclass
class _FakeGapReport:
    ats_score_estimate: int = 82
    top_missing: List[_FakeGapSignal] = field(default_factory=lambda: [_FakeGapSignal()])
    keyword_gaps: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=lambda: ["Add Spark experience"])
    gap_lines: List[str] = field(default_factory=list)


@dataclass
class _FakeTailorResult:
    ats_score: int = 82
    gap_summary: List[str] = field(default_factory=lambda: ["ATS Score: 82/100"])
    report: str = "Strong match on Python and data engineering skills."
    output_path: str = "out/resume.tex"
    profile_dict: dict = field(default_factory=dict)


def _fake_execute_text(**kwargs):
    return _FakeTailorResult()


def _fake_run_analysis(jd_text, resume_text, top_n=5):
    return _FakeGapReport()


@pytest.fixture(autouse=True)
def _reset_rate_buckets():
    """Wipe rate-limit buckets between tests (shared client → same IP every test)."""
    api_server._rate_buckets.clear()
    yield
    api_server._rate_buckets.clear()


@pytest.fixture(autouse=True)
def _patch_pipeline(tmp_path):
    """Patch execute_text and run_analysis so tests never hit the real pipeline."""
    fake_tex = tmp_path / "resume.tex"
    fake_tex.write_text("% fake resume", encoding="utf-8")

    fake_result = _FakeTailorResult(output_path=str(fake_tex))

    with (
        patch.object(api_server, "execute_text", return_value=fake_result),
        patch.object(api_server, "run_analysis", side_effect=_fake_run_analysis),
        patch.object(api_server, "push_version", return_value=None),
    ):
        yield


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

def test_health_check():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "2.0.0"


# ---------------------------------------------------------------------------
# /  (browser UI)
# ---------------------------------------------------------------------------

def test_index_returns_html():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# /generate
# ---------------------------------------------------------------------------

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
    assert isinstance(data["ats_score"], (int, float))
    assert 0 <= data["ats_score"] <= 100
    assert "resume_path" in data
    assert "gap_summary" in data
    assert isinstance(data["gap_summary"], list)
    assert "vault_version" in data


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


def test_generate_empty_jd_returns_422():
    payload = {"jd_text": "   ", "artifact_text": _BLOB, "artifact_format": "blob"}
    resp = client.post("/generate", json=payload, headers=HEADERS)
    assert resp.status_code == 422


def test_generate_empty_artifact_returns_422():
    payload = {"jd_text": _JD, "artifact_text": "   ", "artifact_format": "blob"}
    resp = client.post("/generate", json=payload, headers=HEADERS)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /score
# ---------------------------------------------------------------------------

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

def test_cover_letter_missing_jd_returns_422():
    resp = client.post("/cover-letter", json={"artifact_text": _BLOB}, headers=HEADERS)
    assert resp.status_code == 422


def test_cover_letter_bad_api_key_returns_401():
    payload = {"jd_text": _JD, "artifact_text": _BLOB}
    resp = client.post("/cover-letter", json=payload, headers={"X-API-Key": "nope"})
    assert resp.status_code == 401


def test_cover_letter_happy_path():
    """Cover letter with template method (no Claude API needed)."""
    from cover_letter_renderer import CoverLetterResult
    fake_letter = CoverLetterResult(
        tex=r"\begin{document}Letter\end{document}",
        txt="Dear Hiring Manager, ...",
        docx_path=None,
        word_count=50,
        method_used="template",
    )
    payload = {
        "jd_text": _JD,
        "artifact_text": _BLOB,
        "artifact_format": "blob",
        "name": "Jane Smith",
        "email": "jane@example.com",
        "method": "template",
    }
    with patch.object(api_server, "build_cover_letter", return_value=fake_letter):
        resp = client.post("/cover-letter", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "txt" in data
    assert isinstance(data["txt"], str)
    assert "word_count" in data
    assert "method_used" in data


# ---------------------------------------------------------------------------
# /ingest/github
# ---------------------------------------------------------------------------

def test_ingest_github_happy_path():
    fake_projects = [
        {
            "name": "autoapply-ai", "description": "AI job tool", "bullets": [],
            "tools": ["Python"], "url": "https://github.com/n/autoapply-ai",
            "stars": 42, "source": "github",
        }
    ]
    with patch.object(api_server, "fetch_user_repos", return_value=fake_projects):
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
# Rate limiting
# ---------------------------------------------------------------------------

def test_rate_limit_returns_429_after_limit():
    """Exceed _RATE_LIMIT_PER_MINUTE requests → 429."""
    limit = api_server._RATE_LIMIT_PER_MINUTE
    # Pre-fill the rate bucket to the limit
    import time
    key = _rate_limit_key_for_client()
    now = time.time()
    for _ in range(limit):
        api_server._rate_buckets[key].append(now)

    resp = client.get("/health")  # health is exempt, so hit /score instead
    payload = {"jd_text": _JD, "resume_text": "Spark"}
    resp = client.post("/score", json=payload, headers=HEADERS)
    assert resp.status_code == 429


def _rate_limit_key_for_client() -> str:
    """Return the rate-limit key used by TestClient requests (anonymous IP or 'testclient')."""
    # TestClient uses 'testclient' as the host
    return "anon:testclient"
