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


class TestCreateCoachSessionIncrementsCounter:
    def test_increment_rpc_called_on_create(self, monkeypatch):
        from hr_breaker.services.supabase import SupabaseService

        captured_rpc = []

        class FakeBuilder:
            def insert(self, _payload):
                return self

            def execute(self):
                return MagicMock(
                    data=[{"id": "s1", "user_id": USER, "optimization_run_id": "r1"}]
                )

        class FakeClient:
            def table(self, _name):
                return FakeBuilder()

            def rpc(self, fn, params):
                captured_rpc.append((fn, params))
                return MagicMock(execute=lambda: MagicMock(data=None))

        svc = SupabaseService.__new__(SupabaseService)
        svc._client = FakeClient()
        svc.create_coach_session(USER, "r1")

        assert captured_rpc == [
            ("increment_coach_threads_created_total", {"p_user_id": USER})
        ]


class TestCoachThreadCap:
    def test_free_user_under_cap_can_create(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = _free_profile(threads_used=2)
        fake_supabase.get_optimization_run.return_value = {
            "id": "r1", "user_id": USER, "job_parsed": {}
        }
        fake_supabase.create_coach_session.return_value = {
            "id": "new", "optimization_run_id": "r1", "title": None,
            "last_message_at": None, "created_at": "2026-05-17T00:00:00Z",
            "updated_at": "2026-05-17T00:00:00Z",
        }
        r = client.post("/api/coach/sessions", json={"optimization_run_id": "r1"})
        assert r.status_code == 201

    def test_free_user_at_cap_is_blocked(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = _free_profile(threads_used=3)
        fake_supabase.get_optimization_run.return_value = {
            "id": "r1", "user_id": USER, "job_parsed": {}
        }
        r = client.post("/api/coach/sessions", json={"optimization_run_id": "r1"})
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "coach_thread_limit"
        fake_supabase.create_coach_session.assert_not_called()

    def test_job_hunter_at_cap_is_blocked(self, client, fake_supabase):
        p = _free_profile(threads_used=3)
        p.update(subscription_tier="job_hunter", subscription_status="active")
        fake_supabase.get_profile.return_value = p
        fake_supabase.get_optimization_run.return_value = {
            "id": "r1", "user_id": USER, "job_parsed": {}
        }
        r = client.post("/api/coach/sessions", json={"optimization_run_id": "r1"})
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "coach_thread_limit"

    def test_offer_mode_past_cap_can_create(self, client, fake_supabase):
        p = {**_offer_mode_profile(), "coach_threads_created_total": 999}
        fake_supabase.get_profile.return_value = p
        fake_supabase.get_optimization_run.return_value = {
            "id": "r1", "user_id": USER, "job_parsed": {}
        }
        fake_supabase.create_coach_session.return_value = {
            "id": "new", "optimization_run_id": "r1", "title": None,
            "last_message_at": None, "created_at": "2026-05-17T00:00:00Z",
            "updated_at": "2026-05-17T00:00:00Z",
        }
        r = client.post("/api/coach/sessions", json={"optimization_run_id": "r1"})
        assert r.status_code == 201


class TestCoachChatLazyCreateCap:
    def test_free_user_at_cap_blocked_on_lazy_chat(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = _free_profile(threads_used=3)
        fake_supabase.get_optimization_run.return_value = {
            "id": "r1", "user_id": USER, "job_parsed": {}
        }
        r = client.post(
            "/api/coach/chat", json={"optimization_run_id": "r1", "message": "hi"}
        )
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "coach_thread_limit"


class TestCoachChatTurnCap:
    @staticmethod
    def _history_with_user_turns(n: int) -> list[dict]:
        msgs = []
        for i in range(n):
            msgs.append({
                "kind": "request",
                "parts": [{"part_kind": "user-prompt", "content": f"q{i}"}],
            })
            msgs.append({
                "kind": "response",
                "parts": [{"part_kind": "text", "content": f"a{i}"}],
                "model_name": "test",
                "timestamp": "2026-05-17T00:00:00Z",
            })
        return msgs

    def test_free_user_at_turn_cap_blocked(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = _free_profile(threads_used=1)
        fake_supabase.get_coach_session.return_value = {
            "id": "s1", "user_id": USER, "optimization_run_id": "r1"
        }
        fake_supabase.get_coach_messages.return_value = self._history_with_user_turns(5)
        r = client.post("/api/coach/chat", json={"thread_id": "s1", "message": "hi"})
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "coach_turn_limit"

    def test_offer_mode_past_turn_cap_passes(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = _offer_mode_profile()
        fake_supabase.get_coach_session.return_value = {
            "id": "s1", "user_id": USER, "optimization_run_id": "r1"
        }
        fake_supabase.get_optimization_run.return_value = {
            "id": "r1", "user_id": USER, "job_parsed": {}
        }
        fake_supabase.get_cv.return_value = None
        fake_supabase.get_coach_messages.return_value = self._history_with_user_turns(50)
        r = client.post("/api/coach/chat", json={"thread_id": "s1", "message": "hi"})
        assert r.status_code == 200
