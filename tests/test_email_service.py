"""Tests for EmailService — Resend wrapper."""

from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def patched_settings():
    with patch("hr_breaker.services.email_service.get_settings") as gs:
        gs.return_value = MagicMock(
            resend_api_key="test-key",
            support_email_from="noreply@test.com",
            support_email_to="support@test.com",
        )
        yield gs


def test_send_feedback_notification_calls_resend_with_expected_payload(patched_settings):
    from hr_breaker.services.email_service import EmailService

    with patch("hr_breaker.services.email_service.resend") as fake_resend:
        EmailService().send_feedback_notification(
            feedback_id="fid-1",
            feedback_type="refund",
            user_email="alice@example.com",
            message="please refund me",
            context={"tier": "job_hunter", "status": "active"},
        )

    assert fake_resend.api_key == "test-key"
    fake_resend.Emails.send.assert_called_once()
    payload = fake_resend.Emails.send.call_args[0][0]
    assert payload["from"] == "noreply@test.com"
    assert payload["to"] == ["support@test.com"]
    assert payload["reply_to"] == "alice@example.com"
    assert "[REFUND]" in payload["subject"]
    assert "alice@example.com" in payload["subject"]
    assert "please refund me" in payload["html"]
    assert "job_hunter" in payload["html"]
    assert "fid-1" in payload["html"]


def test_send_feedback_notification_escapes_html_in_message(patched_settings):
    from hr_breaker.services.email_service import EmailService

    with patch("hr_breaker.services.email_service.resend") as fake_resend:
        EmailService().send_feedback_notification(
            feedback_id="fid-2",
            feedback_type="bug",
            user_email="bob@example.com",
            message="<script>alert(1)</script>",
            context={},
        )

    html = fake_resend.Emails.send.call_args[0][0]["html"]
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_send_feedback_notification_omits_reply_to_when_user_email_missing(patched_settings):
    from hr_breaker.services.email_service import EmailService

    with patch("hr_breaker.services.email_service.resend") as fake_resend:
        EmailService().send_feedback_notification(
            feedback_id="fid-3",
            feedback_type="idea",
            user_email=None,
            message="some idea here yes",
            context={},
        )

    payload = fake_resend.Emails.send.call_args[0][0]
    assert "reply_to" not in payload
    assert "no email on file" in payload["html"]


def test_send_feedback_notification_raises_email_service_error_on_resend_failure(patched_settings):
    from hr_breaker.services.email_service import EmailService, EmailServiceError

    with patch("hr_breaker.services.email_service.resend") as fake_resend:
        fake_resend.Emails.send.side_effect = RuntimeError("resend down")
        with pytest.raises(EmailServiceError):
            EmailService().send_feedback_notification(
                feedback_id="fid-4",
                feedback_type="bug",
                user_email="x@y.com",
                message="something broke here yes",
                context={},
            )
