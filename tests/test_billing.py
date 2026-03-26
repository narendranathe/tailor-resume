"""
tests/test_billing.py
Tests for subscription tiers, usage metering, and Stripe billing routes — Issue #41.

Tests:
  - test_usage_get_returns_plan      — GET /api/v1/usage returns {plan, count_this_month, limit}
  - test_checkout_returns_url        — POST /api/v1/billing/checkout returns checkout_url (mock stripe)
  - test_free_limit_enforcement      — after 5 tailors, 6th returns 402
  - test_pro_bypasses_limit          — pro user can tailor > 5 times
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — must happen before any app imports
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent
_BACKEND = _REPO_ROOT / "web_app" / "backend"
_SCRIPTS = _REPO_ROOT / ".claude" / "skills" / "tailor-resume" / "scripts"

for _p in (_BACKEND, _SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(monkeypatch, *, environment="development"):
    """Return a TestClient with dev auth bypass."""
    import importlib
    import app.config as _cfg

    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("CLERK_PEM_KEY", "")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_fake")
    monkeypatch.setenv("STRIPE_PRO_PRICE_ID", "price_fake_pro")

    _cfg.get_settings.cache_clear()

    from fastapi.testclient import TestClient
    from app.main import create_app

    return TestClient(create_app(), raise_server_exceptions=True)


def _fake_usage_store(plan="free", count=0):
    """Return a mock usage store with the given plan and count."""
    store = MagicMock()
    store.get_plan.return_value = plan
    store.get_count.return_value = count
    store.increment.return_value = None
    store.set_plan.return_value = None
    return store


# ---------------------------------------------------------------------------
# GET /usage
# ---------------------------------------------------------------------------

class TestGetUsage:
    def test_usage_get_returns_plan(self, monkeypatch):
        """GET /api/v1/usage returns {plan, count_this_month, limit}."""
        client = _make_client(monkeypatch)

        store = _fake_usage_store(plan="free", count=2)
        monkeypatch.setattr("app.middleware.usage._get_usage_store", lambda: store)

        resp = client.get("/api/v1/usage")
        assert resp.status_code == 200
        body = resp.json()
        assert body["plan"] == "free"
        assert body["count_this_month"] == 2
        assert body["limit"] == 5

    def test_usage_get_pro_has_no_limit(self, monkeypatch):
        """Pro users get limit=null (unlimited)."""
        client = _make_client(monkeypatch)

        store = _fake_usage_store(plan="pro", count=12)
        monkeypatch.setattr("app.middleware.usage._get_usage_store", lambda: store)

        resp = client.get("/api/v1/usage")
        assert resp.status_code == 200
        body = resp.json()
        assert body["plan"] == "pro"
        assert body["limit"] is None


# ---------------------------------------------------------------------------
# POST /billing/checkout
# ---------------------------------------------------------------------------

class TestCheckout:
    def test_checkout_returns_url(self, monkeypatch):
        """POST /api/v1/billing/checkout returns checkout_url when Stripe is mocked."""
        client = _make_client(monkeypatch)

        # has_stripe depends on settings.STRIPE_SECRET_KEY which is bound at import time.
        # Patch the class property so the already-imported settings object returns True.
        from app.config import Settings
        monkeypatch.setattr(Settings, "has_stripe", property(lambda self: True))

        # Mock stripe module (lazy-imported inside the route handler)
        mock_stripe = MagicMock()
        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/pay/cs_test_fake"
        mock_stripe.checkout.Session.create.return_value = mock_session
        monkeypatch.setitem(sys.modules, "stripe", mock_stripe)

        resp = client.post("/api/v1/billing/checkout")
        assert resp.status_code == 200
        body = resp.json()
        assert "checkout_url" in body
        assert body["checkout_url"] == "https://checkout.stripe.com/pay/cs_test_fake"

    def test_checkout_503_when_stripe_not_configured(self, monkeypatch):
        """Returns 503 when STRIPE_SECRET_KEY is not set."""
        import importlib
        import app.config as _cfg

        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("CLERK_PEM_KEY", "")
        monkeypatch.setenv("STRIPE_SECRET_KEY", "")   # empty = not configured
        monkeypatch.setenv("STRIPE_PRO_PRICE_ID", "")

        _cfg.get_settings.cache_clear()

        from fastapi.testclient import TestClient
        from app.main import create_app

        client = TestClient(create_app(), raise_server_exceptions=True)
        resp = client.post("/api/v1/billing/checkout")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Usage limit enforcement
# ---------------------------------------------------------------------------

class TestUsageLimitEnforcement:
    def _client_with_pipeline_patched(self, monkeypatch):
        """Client with pipeline no-op'd so we can focus on usage logic."""
        client = _make_client(monkeypatch)

        fake_result = MagicMock()
        fake_result.ats_score = 0.75
        fake_result.gap_summary = "Missing: Docker"
        fake_result.report = "Good match."
        fake_result.output_path = None

        import app.routes.resume as _route_mod
        monkeypatch.setattr(_route_mod, "_run_pipeline", lambda *a, **kw: fake_result)

        return client

    def _post_tailor(self, client):
        return client.post(
            "/api/v1/resume/tailor",
            data={"jd_text": "Senior data engineer with Spark"},
            files={"artifact": ("resume.txt", b"John Doe\nPython Spark", "text/plain")},
        )

    def test_free_limit_enforcement(self, monkeypatch):
        """After 5 successful tailors, the 6th returns HTTP 402."""
        client = self._client_with_pipeline_patched(monkeypatch)

        # Simulate: user already has 5 uses this month
        store = _fake_usage_store(plan="free", count=5)
        monkeypatch.setattr("app.middleware.usage._get_usage_store", lambda: store)

        resp = self._post_tailor(client)
        assert resp.status_code == 402
        assert "Free tier limit" in resp.json()["detail"]

    def test_free_user_under_limit_succeeds(self, monkeypatch):
        """A free user with count < 5 can still tailor."""
        client = self._client_with_pipeline_patched(monkeypatch)

        store = _fake_usage_store(plan="free", count=3)
        monkeypatch.setattr("app.middleware.usage._get_usage_store", lambda: store)

        resp = self._post_tailor(client)
        assert resp.status_code == 200

    def test_pro_bypasses_limit(self, monkeypatch):
        """Pro users bypass the 5/mo limit even with count > 5."""
        client = self._client_with_pipeline_patched(monkeypatch)

        # Pro user with 10 uses — should still be allowed
        store = _fake_usage_store(plan="pro", count=10)
        monkeypatch.setattr("app.middleware.usage._get_usage_store", lambda: store)

        resp = self._post_tailor(client)
        assert resp.status_code == 200

    def test_increment_called_after_success(self, monkeypatch):
        """increment_usage is called after a successful pipeline run."""
        client = self._client_with_pipeline_patched(monkeypatch)

        store = _fake_usage_store(plan="free", count=2)
        monkeypatch.setattr("app.middleware.usage._get_usage_store", lambda: store)

        resp = self._post_tailor(client)
        assert resp.status_code == 200
        store.increment.assert_called_once()


# ---------------------------------------------------------------------------
# SQLite fallback store unit tests
# ---------------------------------------------------------------------------

class TestSQLiteUsageStore:
    def test_sqlite_store_plan_defaults_free(self, tmp_path):
        """New user in SQLite store defaults to free plan."""
        store = _make_sqlite_store(tmp_path / "usage.db")
        assert store.get_plan("new-user") == "free"
        assert store.get_count("new-user", "2026-03") == 0

    def test_sqlite_store_increment(self, tmp_path):
        store = _make_sqlite_store(tmp_path / "usage.db")
        store.increment("u1", "2026-03")
        store.increment("u1", "2026-03")
        assert store.get_count("u1", "2026-03") == 2

    def test_sqlite_store_set_plan(self, tmp_path):
        store = _make_sqlite_store(tmp_path / "usage.db")
        store.set_plan("u2", "pro", stripe_customer_id="cus_abc")
        assert store.get_plan("u2") == "pro"


def _make_sqlite_store(db_path: Path):
    """Instantiate _SQLiteUsageStore pointing at a specific db_path."""
    import sqlite3
    import app.middleware.usage as mod

    store = object.__new__(mod._SQLiteUsageStore)
    store._conn = sqlite3.connect(str(db_path))
    store._conn.execute("""
        CREATE TABLE IF NOT EXISTS usage (
            user_id TEXT NOT NULL,
            month TEXT NOT NULL,
            resume_count INT NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, month)
        )
    """)
    store._conn.execute("""
        CREATE TABLE IF NOT EXISTS user_plans (
            user_id TEXT PRIMARY KEY,
            plan TEXT NOT NULL DEFAULT 'free',
            stripe_customer_id TEXT
        )
    """)
    store._conn.commit()
    return store
