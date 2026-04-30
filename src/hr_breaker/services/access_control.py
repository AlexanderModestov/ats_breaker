"""Tier-aware access control: feature gates + Free-tier quota."""

from dataclasses import dataclass
from datetime import datetime

from hr_breaker.config import get_settings, logger
from hr_breaker.services.tiers import (
    Feature,
    FEATURE_MIN_TIER,
    FREE_WEEKLY_LIMIT,
    effective_tier,
    has_feature_access,
    maybe_reset_weekly_window,
)


@dataclass
class AccessResult:
    allowed: bool
    remaining: int | None = None
    unlimited: bool = False
    reason: str | None = None
    required_tier: str | None = None
    renewal_date: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "remaining": self.remaining,
            "unlimited": self.unlimited,
            "reason": self.reason,
            "required_tier": self.required_tier,
            "renewal_date": self.renewal_date.isoformat() if self.renewal_date else None,
        }


def _is_unlimited(email: str) -> bool:
    return email.lower() in get_settings().unlimited_users


def check_feature_access(feature: Feature, email: str, profile: dict) -> AccessResult:
    """Tier gate. Returns blocked with required_tier when user's effective tier is too low."""
    if _is_unlimited(email):
        return AccessResult(allowed=True, unlimited=True)
    if has_feature_access(feature, profile):
        return AccessResult(allowed=True)
    return AccessResult(
        allowed=False,
        reason="feature_locked",
        required_tier=FEATURE_MIN_TIER[feature],
    )


def check_quota(email: str, profile: dict) -> AccessResult:
    """Quota gate. Only meaningful for Free tier; lazy-resets the weekly window."""
    if _is_unlimited(email):
        return AccessResult(allowed=True, unlimited=True)
    if effective_tier(profile) != "free":
        return AccessResult(allowed=True, unlimited=True)

    profile = maybe_reset_weekly_window(profile)
    used = profile.get("period_request_count", 0)
    if used >= FREE_WEEKLY_LIMIT:
        reset_at = datetime.fromisoformat(
            profile["weekly_reset_at"].replace("Z", "+00:00")
        )
        return AccessResult(
            allowed=False,
            remaining=0,
            reason="quota_exhausted",
            renewal_date=reset_at,
        )
    return AccessResult(allowed=True, remaining=FREE_WEEKLY_LIMIT - used)


def consume_request(email: str, profile: dict) -> dict:
    """Return profile field updates after a successful optimization. Only Free counts.

    If the weekly window has rolled over, persist the new window alongside the
    increment — otherwise the lazy-reset is in-memory only and the user gets
    unlimited Free use after the first window expires.
    """
    if _is_unlimited(email):
        return {}
    if effective_tier(profile) != "free":
        return {}

    fresh = maybe_reset_weekly_window(profile)
    used = fresh.get("period_request_count", 0)
    updates: dict = {"period_request_count": used + 1}
    if fresh is not profile:
        # maybe_reset_weekly_window returned a new dict → window rolled over
        updates["weekly_reset_at"] = fresh["weekly_reset_at"]
    return updates
