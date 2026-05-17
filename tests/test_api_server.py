"""Tests for api_server.py FastAPI TRACER endpoints."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "skills" / "tailor-resume" / "scripts"))

import api_server  # noqa: E402
from api_server import app  # noqa: E402

client = TestClient(app)
HEADERS = {"X-API-Key": "dev-key"}


@pytest.fixture(autouse=True)
def _reset_rate_buckets():
    """Wipe in-memory rate-limit buckets between tests so the shared TestClient
    (which always presents as the same anonymous IP) does not accumulate across
    unrelated tests."""
    api_server._rate_buckets.clear()
    yield
    api_server._rate_buckets.clear()

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


# ---------------------------------------------------------------------------
# GET /vault/{user_id}
# ---------------------------------------------------------------------------


def _make_vault_entry(name: str = "Acme_Resume_20260517_120000"):
    from vault_client import VaultEntry
    return VaultEntry(
        version_tag="Jane_Acme_Resume",
        filename=name,
        branch="vault/jane",
        company="Acme",
        role="Resume",
        ats_score=82.0,
        committed_at="20260517_120000",
        github_path=f"{name}.tex",
        commit_sha="abc123",
    )


def test_vault_list_happy_path(monkeypatch):
    monkeypatch.setattr(
        "api_server.vault_client.list_versions",
        lambda uid, **_: [_make_vault_entry()],
    )
    resp = client.get("/vault/jane", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "jane"
    assert data["count"] == 1
    assert data["entries"][0]["filename"] == "Acme_Resume_20260517_120000"
    assert data["entries"][0]["version_tag"] == "Jane_Acme_Resume"


def test_vault_list_empty(monkeypatch):
    monkeypatch.setattr("api_server.vault_client.list_versions", lambda uid, **_: [])
    resp = client.get("/vault/nobody", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json() == {"user_id": "nobody", "count": 0, "entries": []}


def test_vault_list_bad_api_key():
    resp = client.get("/vault/jane", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /vault/{user_id}/{filename}
# ---------------------------------------------------------------------------


def test_vault_get_tex_happy_path(monkeypatch):
    monkeypatch.setattr(
        "api_server.vault_client.get_version",
        lambda uid, fn: r"\documentclass{article}\begin{document}hi\end{document}",
    )
    resp = client.get("/vault/jane/Acme_Resume_20260517_120000", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/x-tex")
    assert "attachment" in resp.headers["content-disposition"]
    assert "Acme_Resume_20260517_120000.tex" in resp.headers["content-disposition"]
    assert r"\documentclass" in resp.text


def test_vault_get_tex_not_found(monkeypatch):
    monkeypatch.setattr("api_server.vault_client.get_version", lambda uid, fn: "")
    resp = client.get("/vault/jane/missing", headers=HEADERS)
    assert resp.status_code == 404


def test_vault_get_tex_bad_api_key():
    resp = client.get("/vault/jane/foo", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /vault/{user_id}/{filename}/pdf
# ---------------------------------------------------------------------------


def test_vault_get_pdf_happy_path(monkeypatch):
    monkeypatch.setattr(
        "api_server.vault_client.get_version",
        lambda uid, fn: "\\documentclass{article}\\begin{document}hi\\end{document}",
    )
    monkeypatch.setattr(
        "api_server._compile_pdf",
        lambda path: (_write_fake_pdf(path), None),
    )
    resp = client.get(
        "/vault/jane/Acme_Resume_20260517_120000/pdf?first_name=Jane",
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "Jane.pdf" in resp.headers["content-disposition"]
    assert resp.content.startswith(b"%PDF") or resp.content == b"fake pdf bytes"


def _write_fake_pdf(tex_path: str) -> str:
    pdf_path = tex_path.replace(".tex", ".pdf")
    Path(pdf_path).write_bytes(b"fake pdf bytes")
    return pdf_path


def test_vault_get_pdf_default_filename(monkeypatch):
    monkeypatch.setattr("api_server.vault_client.get_version", lambda uid, fn: r"\dummy")
    monkeypatch.setattr("api_server._compile_pdf", lambda path: (_write_fake_pdf(path), None))
    resp = client.get("/vault/jane/Acme_Resume_20260517_120000/pdf", headers=HEADERS)
    assert resp.status_code == 200
    assert "Acme_Resume_20260517_120000.pdf" in resp.headers["content-disposition"]


def test_vault_get_pdf_not_found(monkeypatch):
    monkeypatch.setattr("api_server.vault_client.get_version", lambda uid, fn: "")
    resp = client.get("/vault/jane/missing/pdf", headers=HEADERS)
    assert resp.status_code == 404


def test_vault_get_pdf_pdflatex_absent_returns_501(monkeypatch):
    monkeypatch.setattr("api_server.vault_client.get_version", lambda uid, fn: r"\dummy")
    monkeypatch.setattr("api_server._compile_pdf", lambda path: (None, None))
    resp = client.get("/vault/jane/Acme_Resume/pdf", headers=HEADERS)
    assert resp.status_code == 501
    body = resp.json()
    # FastAPI wraps dict details under "detail"
    detail = body["detail"]
    assert detail["error"] == "PDF compilation unavailable"
    assert "TeX Live" in detail["detail"]


def test_vault_get_pdf_compile_warning_returns_500(monkeypatch):
    monkeypatch.setattr("api_server.vault_client.get_version", lambda uid, fn: r"\dummy")
    monkeypatch.setattr(
        "api_server._compile_pdf",
        lambda path: (None, "pdflatex exit 1: boom"),
    )
    resp = client.get("/vault/jane/Acme_Resume/pdf", headers=HEADERS)
    assert resp.status_code == 500
    assert "pdflatex" in resp.json()["detail"]


def test_vault_get_pdf_bad_api_key():
    resp = client.get("/vault/jane/foo/pdf", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------


def test_rate_limiter_blocks_21st_request_same_user():
    payload = {
        "jd_text": _JD,
        "resume_text": "Spark Kafka Airflow pipelines.",
    }
    # /score uses the anonymous IP bucket — fire 20 then expect 21st to fail.
    for i in range(api_server._RATE_LIMIT_PER_MINUTE):
        resp = client.post("/score", json=payload, headers=HEADERS)
        assert resp.status_code == 200, f"request {i+1} unexpectedly failed: {resp.status_code}"
    resp = client.post("/score", json=payload, headers=HEADERS)
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    assert int(resp.headers["Retry-After"]) >= 1


def test_rate_limiter_independent_buckets_per_user():
    """Different user_ids must have independent buckets."""
    payload_a = {
        "jd_text": _JD,
        "artifact_text": _BLOB,
        "artifact_format": "blob",
        "user_id": "alice",
    }
    payload_b = {
        "jd_text": _JD,
        "artifact_text": _BLOB,
        "artifact_format": "blob",
        "user_id": "bob",
    }
    # Fill alice's bucket to the limit
    for _ in range(api_server._RATE_LIMIT_PER_MINUTE):
        resp = client.post("/generate", json=payload_a, headers=HEADERS)
        assert resp.status_code == 200
    # alice is now blocked
    resp = client.post("/generate", json=payload_a, headers=HEADERS)
    assert resp.status_code == 429
    # bob still gets through
    resp = client.post("/generate", json=payload_b, headers=HEADERS)
    assert resp.status_code == 200


def test_rate_limiter_evicts_old_entries(monkeypatch):
    """Timestamps older than the window get evicted and free up slots."""
    real_time = api_server.time.time
    fake_now = {"t": real_time()}

    def fake_time():
        return fake_now["t"]

    monkeypatch.setattr(api_server.time, "time", fake_time)

    payload = {"jd_text": _JD, "resume_text": "Spark Kafka."}
    # Fill the bucket
    for _ in range(api_server._RATE_LIMIT_PER_MINUTE):
        resp = client.post("/score", json=payload, headers=HEADERS)
        assert resp.status_code == 200
    # 21st request blocked
    assert client.post("/score", json=payload, headers=HEADERS).status_code == 429
    # Jump forward past the window — all old entries should evict
    fake_now["t"] += api_server._RATE_WINDOW_SECONDS + 1
    resp = client.post("/score", json=payload, headers=HEADERS)
    assert resp.status_code == 200


def test_rate_limiter_health_endpoint_exempt():
    """/health is exempt from rate limiting — hammer it past the threshold."""
    for _ in range(api_server._RATE_LIMIT_PER_MINUTE + 5):
        assert client.get("/health").status_code == 200


# ---------------------------------------------------------------------------
# BackgroundTasks: vault push
# ---------------------------------------------------------------------------


def test_generate_vault_version_is_null_by_default(monkeypatch):
    """Default mode: vault push runs in BackgroundTasks; response sees vault_version=None."""
    called = {"push": False}

    def fake_push(**kwargs):
        called["push"] = True
        from vault_client import VaultEntry
        return VaultEntry(
            version_tag="Jane_Acme_Resume",
            filename="x",
            branch="vault/jane",
            company="Acme",
            role="Resume",
            ats_score=80.0,
            committed_at="t",
            github_path="x.tex",
        )

    monkeypatch.setattr("api_server.push_version", fake_push)
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
    # Background task DID run (TestClient waits for them) but vault_version is
    # still null because we set it before queueing the task.
    assert data["vault_version"] is None
    assert called["push"] is True  # background task fired after response was built


def test_generate_vault_inline_populates_version_tag(monkeypatch):
    """vault_inline=True forces synchronous push; vault_version is set."""
    from vault_client import VaultEntry

    def fake_push(**kwargs):
        return VaultEntry(
            version_tag="Jane_Acme_Resume",
            filename="x",
            branch="vault/jane",
            company="Acme",
            role="Resume",
            ats_score=80.0,
            committed_at="t",
            github_path="x.tex",
        )

    monkeypatch.setattr("api_server.push_version", fake_push)
    payload = {
        "jd_text": _JD,
        "artifact_text": _BLOB,
        "artifact_format": "blob",
        "name": "Jane Smith",
        "email": "jane@example.com",
        "vault_inline": True,
    }
    resp = client.post("/generate", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["vault_version"] == "Jane_Acme_Resume"


def test_generate_vault_inline_swallows_push_failure(monkeypatch):
    """If the inline vault push raises, /generate still returns 200 with vault_version=None."""
    def boom(**kwargs):
        raise RuntimeError("vault is down")

    monkeypatch.setattr("api_server.push_version", boom)
    payload = {
        "jd_text": _JD,
        "artifact_text": _BLOB,
        "artifact_format": "blob",
        "vault_inline": True,
    }
    resp = client.post("/generate", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["vault_version"] is None


def test_vault_push_safe_swallows_exceptions(monkeypatch):
    """The background-task wrapper must never propagate exceptions."""
    def boom(**kwargs):
        raise RuntimeError("vault is down")

    monkeypatch.setattr("api_server.push_version", boom)
    # Should not raise
    api_server._vault_push_safe(
        user_id="jane",
        company="Acme",
        role="Resume",
        tex_content="x",
        metadata={},
        first_name="Jane",
    )
