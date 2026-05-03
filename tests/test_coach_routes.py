"""Tests for /api/coach routes — multi-thread."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from hr_breaker.api.deps import (
    get_current_user,
    get_current_user_email,
    get_supabase_service,
)
from hr_breaker.api.main import app

USER = "user-uuid"
EMAIL = "user@example.com"


def _offer_mode_profile() -> dict:
    return {
        "id": USER,
        "subscription_tier": "offer_mode",
        "subscription_status": "active",
        "current_period_end": "2099-01-01T00:00:00+00:00",
        "period_request_count": 0,
        "weekly_reset_at": "2099-01-01T00:00:00+00:00",
    }


@pytest.fixture
def fake_supabase():
    svc = MagicMock()
    svc.get_profile.return_value = _offer_mode_profile()
    svc.list_coach_sessions.return_value = []
    return svc


@pytest.fixture
def client(fake_supabase):
    app.dependency_overrides[get_supabase_service] = lambda: fake_supabase
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_current_user_email] = lambda: (USER, EMAIL)
    with patch("hr_breaker.services.access_control.get_settings") as s:
        s.return_value.unlimited_users = []
        yield TestClient(app)
    app.dependency_overrides.clear()


def test_list_sessions_returns_preview_and_counts(client, fake_supabase):
    fake_supabase.list_coach_sessions.return_value = [
        {
            "id": "s1",
            "optimization_run_id": "r1",
            "title": None,
            "last_message_at": "2026-05-03T10:00:00Z",
            "created_at": "2026-05-01T10:00:00Z",
            "updated_at": "2026-05-03T10:00:00Z",
            "preview": "tell me about a time...",
            "message_count": 4,
        }
    ]
    r = client.get("/api/coach/sessions")
    assert r.status_code == 200
    body = r.json()
    assert body[0]["preview"] == "tell me about a time..."
    assert body[0]["message_count"] == 4
    assert body[0]["title"] is None
    fake_supabase.list_coach_sessions.assert_called_once_with(USER)


def test_create_thread_returns_session(client, fake_supabase):
    fake_supabase.get_optimization_run.return_value = {
        "id": "r1",
        "user_id": USER,
        "job_parsed": {"title": "PM", "company": "Acme"},
    }
    fake_supabase.create_coach_session.return_value = {
        "id": "new-id",
        "optimization_run_id": "r1",
        "title": None,
        "last_message_at": None,
        "created_at": "2026-05-03T10:00:00Z",
        "updated_at": "2026-05-03T10:00:00Z",
    }
    r = client.post("/api/coach/sessions", json={"optimization_run_id": "r1"})
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == "new-id"
    assert body["message_count"] == 0
    assert body["preview"] is None
    fake_supabase.create_coach_session.assert_called_once_with(USER, "r1")


def test_create_thread_404_when_optimization_run_missing(client, fake_supabase):
    fake_supabase.get_optimization_run.return_value = None
    r = client.post("/api/coach/sessions", json={"optimization_run_id": "missing"})
    assert r.status_code == 404
    fake_supabase.create_coach_session.assert_not_called()
