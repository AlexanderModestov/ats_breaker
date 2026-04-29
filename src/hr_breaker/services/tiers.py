"""Tier definitions, feature matrix, and effective-tier logic."""

from datetime import datetime, timedelta, timezone
from enum import Enum


class Feature(str, Enum):
    OPTIMIZE = "optimize"
    COACH = "coach"
    COVER_LETTER = "cover_letter"
    GAP_ANALYSIS = "gap_analysis"


TIER_RANK: dict[str, int] = {"free": 0, "job_hunter": 1, "offer_mode": 2}

FEATURE_MIN_TIER: dict[Feature, str] = {
    Feature.OPTIMIZE: "free",
    Feature.COACH: "offer_mode",
    Feature.COVER_LETTER: "offer_mode",
    Feature.GAP_ANALYSIS: "offer_mode",
}

FREE_WEEKLY_LIMIT = 3


def _parse_ts(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def effective_tier(profile: dict) -> str:
    """The tier the user can currently *use*, accounting for the cancellation grace period."""
    tier = profile.get("subscription_tier", "free")
    status = profile.get("subscription_status", "none")
    period_end = _parse_ts(profile.get("current_period_end"))
    now = datetime.now(timezone.utc)

    if status == "active":
        return tier
    if status == "cancelled" and period_end and now < period_end:
        return tier
    return "free"


def has_feature_access(feature: Feature, profile: dict) -> bool:
    user_rank = TIER_RANK[effective_tier(profile)]
    needed_rank = TIER_RANK[FEATURE_MIN_TIER[feature]]
    return user_rank >= needed_rank


def maybe_reset_weekly_window(profile: dict) -> dict:
    """Return profile with weekly counter reset if window expired. Pure function."""
    reset_at = _parse_ts(profile.get("weekly_reset_at"))
    now = datetime.now(timezone.utc)
    if reset_at is not None and now < reset_at:
        return profile
    return {
        **profile,
        "period_request_count": 0,
        "weekly_reset_at": (now + timedelta(days=7)).isoformat(),
    }
