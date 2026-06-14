"""Tier-aware access control: feature gates + metered optimization quota."""

from dataclasses import dataclass
from datetime import datetime

from hr_breaker.config import get_settings, logger
from hr_breaker.services.tiers import (
    Feature,
    FEATURE_MIN_TIER,
    effective_tier,
    has_feature_access,
    optimization_limit,
)


@dataclass
class AccessResult:
    allowed: bool
    remaining: int | None = None
    reason: str | None = None
    required_tier: str | None = None
    renewal_date: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "remaining": self.remaining,
            "reason": self.reason,
            "required_tier": self.required_tier,
            "renewal_date": self.renewal_date.isoformat() if self.renewal_date else None,
        }


def _is_unlimited(email: str) -> bool:
    return email.lower() in get_settings().unlimited_users


def _parse_period_end(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def check_feature_access(feature: Feature, email: str, profile: dict) -> AccessResult:
    """Tier gate. Returns blocked with required_tier when user's effective tier is too low."""
    if _is_unlimited(email):
        return AccessResult(allowed=True)
    if has_feature_access(feature, profile):
        return AccessResult(allowed=True)
    return AccessResult(
        allowed=False,
        reason="feature_locked",
        required_tier=FEATURE_MIN_TIER[feature],
    )


def check_optimization_quota(email: str, profile: dict) -> AccessResult:
    """Metered optimization quota for every tier."""
    if _is_unlimited(email):
        return AccessResult(allowed=True, remaining=None)

    limit = optimization_limit(profile)
    used = profile.get("period_request_count", 0)
    remaining = max(0, limit - used)
    # Paid tiers renew at the billing-period end; Free never renews.
    renewal = None
    if effective_tier(profile) != "free":
        renewal = _parse_period_end(profile.get("current_period_end"))

    if used >= limit:
        return AccessResult(
            allowed=False, remaining=0,
            reason="quota_exhausted", renewal_date=renewal,
        )
    return AccessResult(allowed=True, remaining=remaining, renewal_date=renewal)
