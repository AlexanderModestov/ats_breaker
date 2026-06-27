"""Tests for GET /api/subscription — metered quota shape."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from hr_breaker.api.deps import get_current_user, get_current_user_email, get_supabase_service
from hr_breaker.api.main import app

USER = "user-uuid"
EMAIL = "user@example.com"


@pytest.fixture
def fake_supabase() -> MagicMock:
    return MagicMock()


@pytest.fixture
def client(fake_supabase: MagicMock) -> TestClient:
    app.dependency_overrides[get_supabase_service] = lambda: fake_supabase
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_current_user_email] = lambda: (USER, EMAIL)
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestSubscriptionStatusShape:
    def test_free_response(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = {
            "subscription_tier": "free", "subscription_status": "none",
            "current_period_end": None, "period_request_count": 1, "coach_chats_used": 0,
        }
        body = client.get("/api/subscription").json()
        assert body["tier"] == "free"
        assert body["optimizations"] == {"used": 1, "limit": 3, "remaining": 2, "renews_at": None}
        assert body["coach"] == {"chats_used": 0, "chats_limit": 1, "msgs_per_chat": 15}
        assert "is_unlimited" not in body
        assert "weekly_reset_at" not in body

    def test_offer_mode_response(self, client, fake_supabase):
        end = "2099-01-01T00:00:00+00:00"
        fake_supabase.get_profile.return_value = {
            "subscription_tier": "offer_mode", "subscription_status": "active",
            "current_period_end": end, "period_request_count": 12, "coach_chats_used": 3,
        }
        body = client.get("/api/subscription").json()
        assert body["optimizations"] == {"used": 12, "limit": 40, "remaining": 28, "renews_at": end}
        assert body["coach"] == {"chats_used": 3, "chats_limit": 10, "msgs_per_chat": 20}


class TestUpgrade:
    def test_paid_to_paid_upgrade_resets_quota(self, client, fake_supabase):
        # Job Hunter at the cap upgrading to Offer Mode must get fresh quota.
        fake_supabase.get_profile.return_value = {
            "subscription_tier": "job_hunter", "subscription_status": "active",
            "subscription_id": "sub_abc", "period_request_count": 20, "coach_chats_used": 1,
        }
        with patch("hr_breaker.api.routes.subscription.StripeService") as stripe_cls:
            stripe_cls.return_value.upgrade_subscription.return_value = None
            resp = client.post("/api/subscription/upgrade", json={"tier": "offer_mode"})

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        fake_supabase.update_profile.assert_called_once()
        args, _ = fake_supabase.update_profile.call_args
        user_id, updates = args
        assert user_id == USER
        assert updates["subscription_tier"] == "offer_mode"
        assert updates["period_request_count"] == 0
        assert updates["coach_chats_used"] == 0
