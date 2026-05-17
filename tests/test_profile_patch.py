"""
tests/test_profile_patch.py
Tests for PATCH /api/v1/profile — Epic #91 (M4).
"""
from __future__ import annotations

import sys
from pathlib import Path as _Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = _Path(__file__).parent.parent
_BACKEND = _REPO_ROOT / "web_app" / "backend"
_SCRIPTS = _REPO_ROOT / ".claude" / "skills" / "tailor-resume" / "scripts"
for _p in (_BACKEND, _SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("CLERK_PEM_KEY", "")
    import app.config as _cfg
    _cfg.get_settings.cache_clear()
    from app.main import create_app
    return TestClient(create_app(), raise_server_exceptions=True)


@pytest.fixture()
def existing_profile():
    return {
        "header": {"name": "Jane Doe", "email": "jane@example.com"},
        "experience": [{"title": "DE", "company": "Acme"}],
        "skills": ["Python", "Spark"],
        "education": [],
        "projects": [],
        "certifications": [],
    }


class TestPatchProfile:
    def test_404_when_no_profile_stored(self, client, monkeypatch):
        store = MagicMock()
        store.get.return_value = None
        monkeypatch.setattr("app.routes.profile.get_profile_store", lambda: store)
        resp = client.patch("/api/v1/profile", json={"patch": {"header": {"phone": "+1"}}})
        assert resp.status_code == 404

    def test_merges_nested_dict(self, client, existing_profile, monkeypatch):
        store = MagicMock()
        store.get.return_value = existing_profile
        monkeypatch.setattr("app.routes.profile.get_profile_store", lambda: store)
        resp = client.patch(
            "/api/v1/profile",
            json={"patch": {"header": {"phone": "+1-555"}}},
        )
        assert resp.status_code == 200
        body = resp.json()
        # Original name preserved, phone added
        assert body["profile"]["header"]["name"] == "Jane Doe"
        assert body["profile"]["header"]["phone"] == "+1-555"
        store.upsert.assert_called_once()

    def test_list_in_patch_replaces_list_in_storage(self, client, existing_profile, monkeypatch):
        store = MagicMock()
        store.get.return_value = existing_profile
        monkeypatch.setattr("app.routes.profile.get_profile_store", lambda: store)
        resp = client.patch(
            "/api/v1/profile",
            json={"patch": {"skills": ["Rust", "Go"]}},
        )
        assert resp.status_code == 200
        assert resp.json()["profile"]["skills"] == ["Rust", "Go"]

    def test_empty_patch_is_noop_but_200(self, client, existing_profile, monkeypatch):
        store = MagicMock()
        store.get.return_value = existing_profile
        monkeypatch.setattr("app.routes.profile.get_profile_store", lambda: store)
        resp = client.patch("/api/v1/profile", json={"patch": {}})
        assert resp.status_code == 200
        assert resp.json()["profile"]["header"]["name"] == "Jane Doe"
