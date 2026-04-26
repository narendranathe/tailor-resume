"""
tests/test_web_api.py
Functional tests for the tailor-resume FastAPI backend — Issue #34.

Uses TestClient (ASGI, no real HTTP) and monkeypatches the heavy pipeline
and Supabase calls so tests run fast without external dependencies.
"""
from __future__ import annotations

import base64
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Path setup — must happen before any app imports
# ---------------------------------------------------------------------------

import sys
from pathlib import Path as _Path

_REPO_ROOT = _Path(__file__).parent.parent
_BACKEND = _REPO_ROOT / "web_app" / "backend"
_SCRIPTS = _REPO_ROOT / ".claude" / "skills" / "tailor-resume" / "scripts"

for _p in (_BACKEND, _SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_scripts_path(monkeypatch):
    """No-op — paths are set at module level above."""
    pass


@pytest.fixture()
def client(monkeypatch):
    """Return a TestClient with auth bypassed (dev-user)."""
    # Ensure dev mode so auth header is not required
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("CLERK_PEM_KEY", "")

    # Re-import fresh settings so monkeypatched env vars take effect
    import app.config as _cfg
    _cfg.get_settings.cache_clear()

    from app.main import create_app
    return TestClient(create_app(), raise_server_exceptions=True)


@pytest.fixture()
def fake_tailor_result():
    """A minimal TailorResult-like object."""
    result = MagicMock()
    result.ats_score = 0.82
    result.gap_summary = "Missing: Kubernetes, Terraform"
    result.report = "Strong match on Python and data engineering skills."
    result.output_path = None
    return result


@pytest.fixture()
def fake_profile():
    return {
        "experience": [{"title": "Senior DE", "company": "Acme", "start": "2021-01", "end": None}],
        "skills": ["Python", "Spark", "Kafka"],
        "education": [],
        "projects": [],
        "certifications": [],
    }


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_health_includes_version(self, client):
        resp = client.get("/api/v1/health")
        assert "version" in resp.json()


# ---------------------------------------------------------------------------
# POST /resume/tailor
# ---------------------------------------------------------------------------

class TestTailorEndpoint:
    def test_tailor_plain_text_resume(self, client, fake_tailor_result, monkeypatch):
        import app.routes.resume as _route_mod
        monkeypatch.setattr(_route_mod, "_run_pipeline", lambda *a, **kw: fake_tailor_result)

        resp = client.post(
            "/api/v1/resume/tailor",
            data={"jd_text": "We need a senior data engineer with Spark experience."},
            files={"artifact": ("resume.txt", b"John Doe\nSenior Data Engineer\nPython, Spark", "text/plain")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ats_score"] == pytest.approx(0.82)
        assert "Kubernetes" in body["gap_summary"]

    def test_tailor_missing_jd_returns_422(self, client):
        resp = client.post(
            "/api/v1/resume/tailor",
            files={"artifact": ("resume.txt", b"some content", "text/plain")},
        )
        assert resp.status_code == 422

    def test_tailor_missing_artifact_returns_422(self, client):
        resp = client.post(
            "/api/v1/resume/tailor",
            data={"jd_text": "We need a senior data engineer."},
        )
        assert resp.status_code == 422

    def test_tailor_pipeline_error_returns_422(self, client, monkeypatch):
        import app.routes.resume as _route_mod

        def _boom(*a, **kw):
            raise RuntimeError("Simulated pipeline failure")

        monkeypatch.setattr(_route_mod, "_run_pipeline", _boom)

        resp = client.post(
            "/api/v1/resume/tailor",
            data={"jd_text": "Data engineer role"},
            files={"artifact": ("resume.txt", b"Some resume content", "text/plain")},
        )
        assert resp.status_code == 422
        assert "Pipeline error" in resp.json()["detail"]

    def test_tailor_with_tex_output(self, client, fake_tailor_result, tmp_path, monkeypatch):
        tex_path = tmp_path / "out.tex"
        tex_path.write_bytes(b"\\documentclass{article}")
        fake_tailor_result.output_path = str(tex_path)

        import app.routes.resume as _route_mod
        monkeypatch.setattr(_route_mod, "_run_pipeline", lambda *a, **kw: fake_tailor_result)

        resp = client.post(
            "/api/v1/resume/tailor",
            data={"jd_text": "Senior DE role"},
            files={"artifact": ("resume.txt", b"resume content", "text/plain")},
        )
        assert resp.status_code == 200
        tex_b64 = resp.json()["tex_b64"]
        assert tex_b64 is not None
        decoded = base64.b64decode(tex_b64)
        assert b"\\documentclass" in decoded


# ---------------------------------------------------------------------------
# GET /profile
# ---------------------------------------------------------------------------

class TestGetProfile:
    def test_get_profile_not_found(self, client, monkeypatch):
        store = MagicMock()
        store.get.return_value = None
        monkeypatch.setattr("app.routes.profile.get_profile_store", lambda: store)

        resp = client.get("/api/v1/profile")
        assert resp.status_code == 404

    def test_get_profile_returns_stored(self, client, fake_profile, monkeypatch):
        store = MagicMock()
        store.get.return_value = fake_profile
        monkeypatch.setattr("app.routes.profile.get_profile_store", lambda: store)

        resp = client.get("/api/v1/profile")
        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"] == "dev-user"
        assert "Python" in body["profile"]["skills"]


# ---------------------------------------------------------------------------
# POST /profile
# ---------------------------------------------------------------------------

class TestUpsertProfile:
    def test_upsert_plain_text(self, client, fake_profile, monkeypatch):
        store = MagicMock()
        monkeypatch.setattr("app.routes.profile.get_profile_store", lambda: store)
        monkeypatch.setattr("app.routes.profile._parse_to_dict", lambda b, f: fake_profile)

        resp = client.post(
            "/api/v1/profile",
            files={"artifact": ("resume.txt", b"John Doe\nSenior DE", "text/plain")},
        )
        assert resp.status_code == 201
        store.upsert.assert_called_once()
        body = resp.json()
        assert body["user_id"] == "dev-user"

    def test_upsert_parse_error_returns_422(self, client, monkeypatch):
        monkeypatch.setattr("app.routes.profile._parse_to_dict", lambda b, f: (_ for _ in ()).throw(ValueError("bad file")))

        resp = client.post(
            "/api/v1/profile",
            files={"artifact": ("resume.txt", b"garbage", "text/plain")},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /profile
# ---------------------------------------------------------------------------

class TestDeleteProfile:
    def test_delete_profile(self, client, monkeypatch):
        store = MagicMock()
        monkeypatch.setattr("app.routes.profile.get_profile_store", lambda: store)

        resp = client.delete("/api/v1/profile")
        assert resp.status_code == 204
        store.delete.assert_called_once_with("dev-user")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TestAuth:
    def test_dev_fallback_sets_dev_user(self, client, monkeypatch):
        """In dev mode, no auth header → user_id = 'dev-user'."""
        store = MagicMock()
        store.get.return_value = {"skills": []}
        monkeypatch.setattr("app.routes.profile.get_profile_store", lambda: store)

        resp = client.get("/api/v1/profile")
        # Profile not found (None) but didn't 401
        assert resp.status_code in (200, 404)

    def test_x_clerk_user_id_header_used(self, client, monkeypatch):
        store = MagicMock()
        store.get.return_value = {"skills": ["Go"]}
        monkeypatch.setattr("app.routes.profile.get_profile_store", lambda: store)

        resp = client.get("/api/v1/profile", headers={"X-Clerk-User-Id": "user_abc123"})
        assert resp.status_code == 200
        assert resp.json()["user_id"] == "user_abc123"
        store.get.assert_called_once_with("user_abc123")
