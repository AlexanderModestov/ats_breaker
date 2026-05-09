"""Resend email wrapper. Used by /api/feedback to notify the support team."""

from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Literal

import resend

from hr_breaker.config import get_settings, logger


FeedbackType = Literal["refund", "bug", "idea"]


class EmailServiceError(Exception):
    """Raised when Resend send fails."""


class EmailService:
    """Thin wrapper over the Resend Python SDK."""

    def __init__(self) -> None:
        settings = get_settings()
        resend.api_key = settings.resend_api_key
        self._from = settings.support_email_from
        self._to = settings.support_email_to

    def send_feedback_notification(
        self,
        *,
        feedback_id: str,
        feedback_type: FeedbackType,
        user_email: str | None,
        message: str,
        context: dict,
    ) -> None:
        subject = f"[{feedback_type.upper()}] from {user_email or 'unknown user'}"
        body_html = _render_feedback_html(
            feedback_id=feedback_id,
            feedback_type=feedback_type,
            user_email=user_email,
            message=message,
            context=context,
        )

        payload: dict = {
            "from": self._from,
            "to": [self._to],
            "subject": subject,
            "html": body_html,
        }
        if user_email:
            payload["reply_to"] = user_email

        try:
            resend.Emails.send(payload)
        except Exception as e:
            logger.warning("Resend send failed for feedback %s: %s", feedback_id, e)
            raise EmailServiceError(str(e)) from e


def _render_feedback_html(
    *,
    feedback_id: str,
    feedback_type: str,
    user_email: str | None,
    message: str,
    context: dict,
) -> str:
    submitted_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    safe_message = html.escape(message)
    user_line = html.escape(user_email) if user_email else "no email on file"

    context_lines: list[str] = []
    for key in ("tier", "status", "current_period_end", "stripe_customer_id"):
        value = context.get(key)
        if value is not None:
            context_lines.append(
                f"  {html.escape(key)}: {html.escape(str(value))}"
            )
    context_block = "\n".join(context_lines) or "  (no subscription context)"

    return (
        "<pre style='font-family: ui-monospace, monospace; font-size: 13px;'>"
        f"Type: {html.escape(feedback_type)}\n"
        f"User: {user_line}\n"
        f"Submitted: {submitted_at}\n"
        f"Feedback ID: {html.escape(feedback_id)}\n\n"
        f"Subscription context:\n{context_block}\n\n"
        "Message:\n"
        "─────────────────────────────────\n"
        f"{safe_message}\n"
        "─────────────────────────────────\n\n"
        "Reply directly to this email — it goes to the user.</pre>"
    )
