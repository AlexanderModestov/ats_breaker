"""User feedback endpoint — refund / bug / idea submissions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from hr_breaker.api.deps import CurrentUserWithEmail, SupabaseServiceDep
from hr_breaker.config import logger
from hr_breaker.services.email_service import EmailService, EmailServiceError

router = APIRouter()

RATE_LIMIT_WINDOW = timedelta(hours=1)
RATE_LIMIT_MAX = 5


class FeedbackRequest(BaseModel):
    type: Literal["refund", "bug", "idea"]
    message: str = Field(min_length=10, max_length=4000)

    @field_validator("message")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 10:
            raise ValueError("Message must be at least 10 characters")
        return v


class FeedbackResponse(BaseModel):
    ok: bool


def _build_context(profile: dict, user_email: str | None) -> dict:
    return {
        "tier": profile.get("subscription_tier"),
        "status": profile.get("subscription_status"),
        "current_period_end": profile.get("current_period_end"),
        "stripe_customer_id": profile.get("stripe_customer_id"),
        "user_email": user_email,
    }


@router.post("", response_model=FeedbackResponse)
async def submit_feedback(
    body: FeedbackRequest,
    user: CurrentUserWithEmail,
    supabase: SupabaseServiceDep,
) -> FeedbackResponse:
    user_id, user_email = user

    window_start = (datetime.now(timezone.utc) - RATE_LIMIT_WINDOW).isoformat()
    recent = (
        supabase.client.table("user_feedback")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .gte("created_at", window_start)
        .execute()
    )
    if (recent.count or 0) >= RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail="Too many feedback submissions, try again later",
        )

    profile = supabase.get_profile(user_id) or {}
    context = _build_context(profile, user_email)

    insert_result = (
        supabase.client.table("user_feedback")
        .insert(
            {
                "user_id": user_id,
                "type": body.type,
                "message": body.message,
                "context": context,
            }
        )
        .execute()
    )
    feedback_id = insert_result.data[0]["id"]

    try:
        EmailService().send_feedback_notification(
            feedback_id=feedback_id,
            feedback_type=body.type,
            user_email=user_email,
            message=body.message,
            context=context,
        )
        supabase.client.table("user_feedback").update(
            {"email_sent_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", feedback_id).execute()
    except EmailServiceError as e:
        logger.warning("Feedback %s saved but email failed: %s", feedback_id, e)

    return FeedbackResponse(ok=True)
