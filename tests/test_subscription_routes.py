"""Tests for GET /api/subscription — coach quota block."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from hr_breaker.api.deps import get_current_user, get_current_user_email, get_supabase_service
from hr_breaker.api.main import app

USER = "user-uuid"
EMAIL = "user@example.com"


def _free_profile(threads_used: int = 0) -> dict:
    return {
        "id": USER,
        "subscription_tier": "free",
        "subscription_status": "none",
        "current_period_end": None,
        "period_request_count": 0,
        "weekly_reset_at": "2099-01-01T00:00:00+00:00",
        "coach_threads_created_total": threads_used,
    }


def _offer_mode_profile() -> dict:
    return {
        "id": USER,
        "subscription_tier": "offer_mode",
        "subscription_status": "active",
        "current_period_end": "2099-01-01T00:00:00+00:00",
        "period_request_count": 0,
        "weekly_reset_at": "2099-01-01T00:00:00+00:00",
        "coach_threads_created_total": 0,
    }


def _make_client(profile: dict) -> TestClient:
    fake_supabase = MagicMock()
    fake_supabase.get_profile.return_value = profile
    app.dependency_overrides[get_supabase_service] = lambda: fake_supabase
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_current_user_email] = lambda: (USER, EMAIL)
    with patch("hr_breaker.services.access_control.get_settings") as s:
        s.return_value.unlimited_users = []
        client = TestClient(app)
        yield client
    app.dependency_overrides.clear()


class TestSubscriptionCoachBlock:
    def test_free_user_includes_coach_block(self):
        for client in _make_client(_free_profile(threads_used=1)):
            r = client.get("/api/subscription")
        assert r.status_code == 200
        body = r.json()
        assert body["coach"] == {
            "is_unlimited": False,
            "threads_remaining": 2,
            "threads_total": 3,
        }

    def test_free_user_at_cap_remaining_is_zero(self):
        for client in _make_client(_free_profile(threads_used=5)):
            r = client.get("/api/subscription")
        body = r.json()
        assert body["coach"]["threads_remaining"] == 0

    def test_offer_mode_coach_block_is_unlimited(self):
        profile = {**_offer_mode_profile(), "coach_threads_created_total": 99}
        for client in _make_client(profile):
            r = client.get("/api/subscription")
        body = r.json()
        assert body["coach"]["is_unlimited"] is True
        assert body["coach"]["threads_remaining"] == 0
        assert body["coach"]["threads_total"] == 3
