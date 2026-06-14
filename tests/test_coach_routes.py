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


def test_rename_thread_updates_title(client, fake_supabase):
    fake_supabase.update_coach_session_title.return_value = {
        "id": "s1",
        "optimization_run_id": "r1",
        "title": "STAR conflict story",
        "last_message_at": "2026-05-03T10:00:00Z",
        "created_at": "2026-05-01T10:00:00Z",
        "updated_at": "2026-05-03T10:05:00Z",
    }
    r = client.patch("/api/coach/sessions/s1", json={"title": "STAR conflict story"})
    assert r.status_code == 200
    assert r.json()["title"] == "STAR conflict story"
    fake_supabase.update_coach_session_title.assert_called_once_with(
        "s1", USER, "STAR conflict story"
    )


def test_rename_other_users_thread_returns_404(client, fake_supabase):
    fake_supabase.update_coach_session_title.return_value = None
    r = client.patch("/api/coach/sessions/foreign", json={"title": "x"})
    assert r.status_code == 404


def test_delete_thread_returns_204(client, fake_supabase):
    fake_supabase.delete_coach_session.return_value = True
    r = client.delete("/api/coach/sessions/s1")
    assert r.status_code == 204
    fake_supabase.delete_coach_session.assert_called_once_with("s1", USER)


def test_delete_other_users_thread_returns_404(client, fake_supabase):
    fake_supabase.delete_coach_session.return_value = False
    r = client.delete("/api/coach/sessions/foreign")
    assert r.status_code == 404


def test_chat_validates_exactly_one_target(client):
    # Both → 422
    r = client.post(
        "/api/coach/chat",
        json={"thread_id": "t", "optimization_run_id": "r", "message": "hi"},
    )
    assert r.status_code == 422
    # Neither → 422
    r = client.post("/api/coach/chat", json={"message": "hi"})
    assert r.status_code == 422


def _profile(tier="free", status="none", chats_used=0, period_end=None):
    return {
        "id": USER, "subscription_tier": tier, "subscription_status": status,
        "current_period_end": period_end, "coach_chats_used": chats_used,
    }


class TestCoachChatCap:
    def test_free_under_cap_can_create(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = _profile(chats_used=0)
        fake_supabase.consume_coach_chat_quota.return_value = True
        fake_supabase.get_optimization_run.return_value = {"id": "r1", "user_id": USER, "job_parsed": {}}
        fake_supabase.create_coach_session.return_value = {
            "id": "s1", "optimization_run_id": "r1", "title": None,
            "last_message_at": None, "created_at": "2026-06-14T00:00:00Z",
            "updated_at": "2026-06-14T00:00:00Z",
        }
        r = client.post("/api/coach/sessions", json={"optimization_run_id": "r1"})
        assert r.status_code == 201
        fake_supabase.consume_coach_chat_quota.assert_called_once_with(USER, 1)

    def test_free_at_cap_blocked(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = _profile(chats_used=1)
        fake_supabase.consume_coach_chat_quota.return_value = False
        fake_supabase.get_optimization_run.return_value = {"id": "r1", "user_id": USER, "job_parsed": {}}
        r = client.post("/api/coach/sessions", json={"optimization_run_id": "r1"})
        assert r.status_code == 402
        assert r.json()["detail"]["code"] == "coach_chat_limit"
        fake_supabase.create_coach_session.assert_not_called()

    def test_bad_run_does_not_burn_chat_slot(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = _profile(chats_used=0)
        fake_supabase.get_optimization_run.return_value = None
        r = client.post("/api/coach/sessions", json={"optimization_run_id": "missing"})
        assert r.status_code == 404
        fake_supabase.consume_coach_chat_quota.assert_not_called()

    def test_offer_mode_cap_is_10(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = _profile(tier="offer_mode", status="active", chats_used=3)
        fake_supabase.consume_coach_chat_quota.return_value = True
        fake_supabase.get_optimization_run.return_value = {"id": "r1", "user_id": USER, "job_parsed": {}}
        fake_supabase.create_coach_session.return_value = {
            "id": "s1", "optimization_run_id": "r1", "title": None, "last_message_at": None,
            "created_at": "2026-06-14T00:00:00Z", "updated_at": "2026-06-14T00:00:00Z",
        }
        r = client.post("/api/coach/sessions", json={"optimization_run_id": "r1"})
        assert r.status_code == 201
        fake_supabase.consume_coach_chat_quota.assert_called_once_with(USER, 10)

    def test_lazy_create_at_cap_blocked(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = _profile(chats_used=1)
        fake_supabase.consume_coach_chat_quota.return_value = False
        fake_supabase.get_optimization_run.return_value = {"id": "r1", "user_id": USER, "job_parsed": {}}
        r = client.post(
            "/api/coach/chat", json={"optimization_run_id": "r1", "message": "hi"}
        )
        assert r.status_code == 402
        assert r.json()["detail"]["code"] == "coach_chat_limit"
        fake_supabase.create_coach_session.assert_not_called()


class TestCoachTurnCap:
    @staticmethod
    def _history(n_user_turns: int) -> list[dict]:
        msgs = []
        for i in range(n_user_turns):
            msgs.append({"kind": "request", "parts": [{"part_kind": "user-prompt", "content": f"q{i}"}]})
            msgs.append({
                "kind": "response", "parts": [{"part_kind": "text", "content": f"a{i}"}],
                "model_name": "test", "timestamp": "2026-06-14T00:00:00Z",
            })
        return msgs

    def test_free_under_turn_cap_passes(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = _profile(chats_used=1)
        fake_supabase.get_coach_session.return_value = {"id": "s1", "user_id": USER, "optimization_run_id": "r1"}
        fake_supabase.get_optimization_run.return_value = {"id": "r1", "user_id": USER, "job_parsed": {}}
        fake_supabase.get_cv.return_value = None
        fake_supabase.get_coach_messages.return_value = self._history(14)
        r = client.post("/api/coach/chat", json={"thread_id": "s1", "message": "hi"})
        assert r.status_code == 200

    def test_free_at_turn_cap_blocked(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = _profile(chats_used=1)
        fake_supabase.get_coach_session.return_value = {"id": "s1", "user_id": USER, "optimization_run_id": "r1"}
        fake_supabase.get_coach_messages.return_value = self._history(15)
        r = client.post("/api/coach/chat", json={"thread_id": "s1", "message": "hi"})
        assert r.status_code == 402
        assert r.json()["detail"]["code"] == "coach_turn_limit"

    def test_offer_mode_turn_cap_is_20(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = _profile(tier="offer_mode", status="active", chats_used=1)
        fake_supabase.get_coach_session.return_value = {"id": "s1", "user_id": USER, "optimization_run_id": "r1"}
        fake_supabase.get_coach_messages.return_value = self._history(19)
        fake_supabase.get_optimization_run.return_value = {"id": "r1", "user_id": USER, "job_parsed": {}}
        fake_supabase.get_cv.return_value = None
        r = client.post("/api/coach/chat", json={"thread_id": "s1", "message": "hi"})
        assert r.status_code == 200
