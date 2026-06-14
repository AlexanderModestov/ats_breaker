"""Tests for GET /api/subscription — metered quota shape."""

from unittest.mock import MagicMock

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
