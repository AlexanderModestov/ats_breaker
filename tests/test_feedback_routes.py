"""Tests for /api/feedback route."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from hr_breaker.api.deps import (
    get_current_user_email,
    get_supabase_service,
)
from hr_breaker.api.main import app

USER = "user-uuid"
EMAIL = "user@example.com"


def _profile() -> dict:
    return {
        "id": USER,
        "subscription_tier": "job_hunter",
        "subscription_status": "active",
        "current_period_end": "2099-01-01T00:00:00+00:00",
        "stripe_customer_id": "cus_test",
    }


def _make_table_mock(rate_count: int = 0):
    """Build a chainable Supabase table mock with insert/select/update."""
    table_mock = MagicMock()

    insert_chain = MagicMock()
    insert_chain.execute.return_value = MagicMock(data=[{"id": "fid-x"}])
    table_mock.insert.return_value = insert_chain

    select_chain = MagicMock()
    select_chain.eq.return_value.gte.return_value.execute.return_value = MagicMock(
        count=rate_count
    )
    table_mock.select.return_value = select_chain

    update_chain = MagicMock()
    update_chain.eq.return_value.execute.return_value = MagicMock(data=[])
    table_mock.update.return_value = update_chain

    return table_mock


@pytest.fixture
def fake_supabase():
    svc = MagicMock()
    svc.get_profile.return_value = _profile()
    table_mock = _make_table_mock(rate_count=0)
    svc.client.table.return_value = table_mock
    svc._table_mock = table_mock
    return svc


@pytest.fixture
def client(fake_supabase):
    app.dependency_overrides[get_supabase_service] = lambda: fake_supabase
    app.dependency_overrides[get_current_user_email] = lambda: (USER, EMAIL)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_submit_feedback_creates_row_and_sends_email(client, fake_supabase):
    with patch("hr_breaker.api.routes.feedback.EmailService") as fake_email_cls:
        instance = fake_email_cls.return_value
        resp = client.post(
            "/api/feedback",
            json={"type": "refund", "message": "please refund my last payment"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    insert_call = fake_supabase._table_mock.insert.call_args[0][0]
    assert insert_call["type"] == "refund"
    assert insert_call["user_id"] == USER
    assert insert_call["message"] == "please refund my last payment"
    assert insert_call["context"]["tier"] == "job_hunter"
    assert insert_call["context"]["user_email"] == EMAIL
    instance.send_feedback_notification.assert_called_once()
    fake_supabase._table_mock.update.assert_called_once()


def test_submit_feedback_too_short_returns_422(client):
    resp = client.post("/api/feedback", json={"type": "bug", "message": "short"})
    assert resp.status_code == 422


def test_submit_feedback_too_long_returns_422(client):
    resp = client.post(
        "/api/feedback",
        json={"type": "bug", "message": "x" * 4001},
    )
    assert resp.status_code == 422


def test_submit_feedback_invalid_type_returns_422(client):
    resp = client.post(
        "/api/feedback",
        json={"type": "spam", "message": "valid length message here"},
    )
    assert resp.status_code == 422


def test_submit_feedback_unauthenticated_returns_401():
    app.dependency_overrides.clear()
    c = TestClient(app)
    resp = c.post(
        "/api/feedback",
        json={"type": "idea", "message": "some valid idea here"},
    )
    assert resp.status_code == 401


def test_rate_limit_after_5_requests_returns_429(client, fake_supabase):
    # Override the count to simulate 5 prior submissions in last hour.
    fake_supabase.client.table.return_value = _make_table_mock(rate_count=5)
    with patch("hr_breaker.api.routes.feedback.EmailService"):
        resp = client.post(
            "/api/feedback",
            json={"type": "idea", "message": "some valid idea text here"},
        )
    assert resp.status_code == 429


def test_email_failure_still_persists_and_returns_200(client, fake_supabase):
    from hr_breaker.services.email_service import EmailServiceError

    with patch("hr_breaker.api.routes.feedback.EmailService") as fake_email_cls:
        fake_email_cls.return_value.send_feedback_notification.side_effect = (
            EmailServiceError("resend down")
        )
        resp = client.post(
            "/api/feedback",
            json={"type": "bug", "message": "something broke for me"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    fake_supabase._table_mock.insert.assert_called_once()
    fake_supabase._table_mock.update.assert_not_called()


def test_message_is_stripped(client, fake_supabase):
    with patch("hr_breaker.api.routes.feedback.EmailService"):
        resp = client.post(
            "/api/feedback",
            json={
                "type": "idea",
                "message": "   leading and trailing whitespace here   ",
            },
        )
    assert resp.status_code == 200
    insert_call = fake_supabase._table_mock.insert.call_args[0][0]
    assert insert_call["message"] == "leading and trailing whitespace here"
