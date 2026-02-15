"""Access control service for paywall enforcement."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from hr_breaker.config import get_settings, logger


@dataclass
class AccessResult:
    """Result of an access check."""

    allowed: bool
    remaining: int | None = None
    unlimited: bool = False
    is_trial: bool = False
    reason: str | None = None
    can_subscribe: bool = False
    can_buy_addon: bool = False
    renewal_date: datetime | None = None


def check_access(user_email: str, profile: dict[str, Any]) -> AccessResult:
    """
    Check if a user has access to make optimization requests.

    Args:
        user_email: The user's email address
        profile: The user's profile data from database

    Returns:
        AccessResult with access decision and details
    """
    settings = get_settings()

    # 1. Admin override - unlimited access
    logger.info(f"Checking access for email='{user_email}', unlimited_users={settings.unlimited_users}")
    if user_email.lower() in settings.unlimited_users:
        logger.info(f"User {user_email} has unlimited access")
        return AccessResult(allowed=True, unlimited=True)

    subscription_status = profile.get("subscription_status", "trial")
    current_period_end = profile.get("current_period_end")
    period_request_count = profile.get("period_request_count", 0)
    addon_credits = profile.get("addon_credits", 0)
    request_count = profile.get("request_count", 0)

    # Parse current_period_end if it's a string
    if isinstance(current_period_end, str):
        current_period_end = datetime.fromisoformat(current_period_end.replace("Z", "+00:00"))

    now = datetime.now(timezone.utc)

    # 2. Active or cancelled-but-paid-through subscriber
    if subscription_status in ("active", "cancelled") and current_period_end and now < current_period_end:
        remaining_period = settings.subscription_request_limit - period_request_count
        remaining_total = remaining_period + addon_credits

        if remaining_total > 0:
            return AccessResult(
                allowed=True,
                remaining=remaining_total,
                renewal_date=current_period_end,
            )
        else:
            return AccessResult(
                allowed=False,
                remaining=0,
                reason="quota_exhausted",
                can_buy_addon=True,
                renewal_date=current_period_end,
            )

    # 3. Trial user
    if request_count < settings.trial_request_limit:
        remaining = settings.trial_request_limit - request_count
        return AccessResult(
            allowed=True,
            remaining=remaining,
            is_trial=True,
        )

    # 4. Trial exhausted, no active subscription
    return AccessResult(
        allowed=False,
        remaining=0,
        reason="trial_exhausted",
        can_subscribe=True,
    )


def consume_request(user_email: str, profile: dict[str, Any]) -> dict[str, Any]:
    """
    Calculate the profile updates needed after consuming a request.

    Args:
        user_email: The user's email address
        profile: The user's profile data from database

    Returns:
        Dict of fields to update in the profile
    """
    settings = get_settings()

    # Admin users don't consume requests
    if user_email.lower() in settings.unlimited_users:
        return {}

    subscription_status = profile.get("subscription_status", "trial")
    period_request_count = profile.get("period_request_count", 0)
    addon_credits = profile.get("addon_credits", 0)
    request_count = profile.get("request_count", 0)

    if subscription_status == "active":
        # Subscriber: use period quota first, then addon credits
        if period_request_count < settings.subscription_request_limit:
            return {"period_request_count": period_request_count + 1}
        elif addon_credits > 0:
            return {"addon_credits": addon_credits - 1}
    else:
        # Trial user: increment lifetime counter
        return {"request_count": request_count + 1}

    return {}
