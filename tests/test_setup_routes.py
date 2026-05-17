"""
tests/test_setup_routes.py
Functional tests for the setup wizard API — Epic #91 (M3).

Mirrors test_web_api.py: TestClient + dev-mode auth bypass + monkeypatched store.
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
def fake_store(monkeypatch):
    store = MagicMock()
    store.get_setup_state.return_value = {
        "target_roles": [],
        "target_companies": [],
        "setup_completed_at": None,
        "setup_skipped_at": None,
        "setup_progress_step": "welcome",
    }
    monkeypatch.setattr("app.routes.setup.get_profile_store", lambda: store)
    return store


# ---------------------------------------------------------------------------
# GET /setup/state
# ---------------------------------------------------------------------------

class TestSetupState:
    def test_returns_default_state_for_new_user(self, client, fake_store):
        resp = client.get("/api/v1/setup/state")
        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"] == "dev-user"
        assert body["target_roles"] == []
        assert body["target_companies"] == []
        assert body["setup_completed_at"] is None
        assert body["setup_progress_step"] == "welcome"

    def test_returns_stored_state(self, client, fake_store):
        fake_store.get_setup_state.return_value = {
            "target_roles": ["Senior Data Engineer"],
            "target_companies": [{"name": "Stripe", "source": "canonical"}],
            "setup_completed_at": "2026-05-01T12:00:00Z",
            "setup_skipped_at": None,
            "setup_progress_step": "complete",
        }
        resp = client.get("/api/v1/setup/state")
        assert resp.status_code == 200
        assert resp.json()["target_roles"] == ["Senior Data Engineer"]
        assert resp.json()["setup_completed_at"] == "2026-05-01T12:00:00Z"


# ---------------------------------------------------------------------------
# PUT /setup/roles
# ---------------------------------------------------------------------------

class TestPutRoles:
    def test_accepts_valid_roles(self, client, fake_store):
        resp = client.put(
            "/api/v1/setup/roles",
            json={"roles": ["Senior Data Engineer", "Staff Data Engineer"]},
        )
        assert resp.status_code == 200
        fake_store.update_setup_state.assert_called_once()
        kwargs = fake_store.update_setup_state.call_args.kwargs
        assert kwargs["target_roles"] == ["Senior Data Engineer", "Staff Data Engineer"]
        assert kwargs["setup_progress_step"] == "companies"

    def test_rejects_empty_roles(self, client, fake_store):
        resp = client.put("/api/v1/setup/roles", json={"roles": []})
        assert resp.status_code == 422

    def test_rejects_more_than_five_roles(self, client, fake_store):
        resp = client.put(
            "/api/v1/setup/roles",
            json={"roles": [f"Role {i}" for i in range(6)]},
        )
        assert resp.status_code == 422

    def test_strips_blank_role_entries(self, client, fake_store):
        resp = client.put(
            "/api/v1/setup/roles",
            json={"roles": ["Senior DE", "   ", "Staff DE"]},
        )
        assert resp.status_code == 200
        kwargs = fake_store.update_setup_state.call_args.kwargs
        assert kwargs["target_roles"] == ["Senior DE", "Staff DE"]


# ---------------------------------------------------------------------------
# PUT /setup/companies
# ---------------------------------------------------------------------------

class TestPutCompanies:
    def test_accepts_valid_companies(self, client, fake_store):
        resp = client.put(
            "/api/v1/setup/companies",
            json={"companies": [
                {"name": "Stripe", "source": "canonical"},
                {"name": "Acme Robotics", "source": "custom"},
            ]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["soft_warning"] is None
        kwargs = fake_store.update_setup_state.call_args.kwargs
        assert kwargs["target_companies"][0]["name"] == "Stripe"
        assert kwargs["setup_progress_step"] == "resume"

    def test_rejects_empty_companies(self, client, fake_store):
        resp = client.put("/api/v1/setup/companies", json={"companies": []})
        assert resp.status_code == 422

    def test_rejects_more_than_100_companies(self, client, fake_store):
        resp = client.put(
            "/api/v1/setup/companies",
            json={"companies": [{"name": f"Co{i}", "source": "custom"} for i in range(101)]},
        )
        assert resp.status_code == 422

    def test_soft_warns_above_50(self, client, fake_store):
        resp = client.put(
            "/api/v1/setup/companies",
            json={"companies": [{"name": f"Co{i}", "source": "custom"} for i in range(60)]},
        )
        assert resp.status_code == 200
        assert resp.json()["soft_warning"] is not None
        assert "60" in resp.json()["soft_warning"] or "50" in resp.json()["soft_warning"]

    def test_defaults_source_to_custom(self, client, fake_store):
        resp = client.put(
            "/api/v1/setup/companies",
            json={"companies": [{"name": "Stripe"}]},
        )
        assert resp.status_code == 200
        kwargs = fake_store.update_setup_state.call_args.kwargs
        assert kwargs["target_companies"][0]["source"] == "custom"


# ---------------------------------------------------------------------------
# POST /setup/complete + /setup/skip
# ---------------------------------------------------------------------------

class TestCompleteSkip:
    def test_complete_sets_timestamp(self, client, fake_store):
        resp = client.post("/api/v1/setup/complete")
        assert resp.status_code == 200
        kwargs = fake_store.update_setup_state.call_args.kwargs
        assert "setup_completed_at" in kwargs
        assert kwargs["setup_progress_step"] == "complete"

    def test_skip_sets_timestamp(self, client, fake_store):
        resp = client.post("/api/v1/setup/skip")
        assert resp.status_code == 200
        kwargs = fake_store.update_setup_state.call_args.kwargs
        assert "setup_skipped_at" in kwargs


# ---------------------------------------------------------------------------
# Store fallback — SQLite path
# ---------------------------------------------------------------------------

class TestSqliteStoreSetupState:
    def test_get_returns_defaults_for_unknown_user(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        from app.db.supabase import _SQLiteProfileStore
        store = _SQLiteProfileStore()
        state = store.get_setup_state("nobody")
        assert state["target_roles"] == []
        assert state["target_companies"] == []
        assert state["setup_completed_at"] is None
        assert state["setup_progress_step"] == "welcome"

    def test_update_then_get_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        from app.db.supabase import _SQLiteProfileStore
        store = _SQLiteProfileStore()
        store.update_setup_state(
            "alice",
            target_roles=["Senior DE"],
            target_companies=[{"name": "Stripe", "source": "canonical"}],
            setup_progress_step="resume",
        )
        state = store.get_setup_state("alice")
        assert state["target_roles"] == ["Senior DE"]
        assert state["target_companies"][0]["name"] == "Stripe"
        assert state["setup_progress_step"] == "resume"
        assert state["setup_completed_at"] is None

    def test_complete_writes_iso_timestamp(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        from app.db.supabase import _SQLiteProfileStore
        store = _SQLiteProfileStore()
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat()
        store.update_setup_state("alice", setup_completed_at=ts)
        state = store.get_setup_state("alice")
        assert state["setup_completed_at"] == ts
