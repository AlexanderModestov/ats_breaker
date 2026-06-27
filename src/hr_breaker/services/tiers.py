"""Tier definitions, feature matrix, and effective-tier logic."""

from datetime import datetime, timezone
from enum import Enum


class Feature(str, Enum):
    OPTIMIZE = "optimize"
    COACH = "coach"
    COVER_LETTER = "cover_letter"
    GAP_ANALYSIS = "gap_analysis"


TIER_RANK: dict[str, int] = {"free": 0, "job_hunter": 1, "offer_mode": 2}

FEATURE_MIN_TIER: dict[Feature, str] = {
    Feature.OPTIMIZE: "free",
    Feature.COACH: "free",  # was "offer_mode" — quota gates the trial now
    Feature.COVER_LETTER: "offer_mode",
    Feature.GAP_ANALYSIS: "offer_mode",
}

TIER_LIMITS: dict[str, dict[str, int]] = {
    "free":       {"optimizations": 3,  "coach_chats": 1,  "coach_msgs": 15},
    "job_hunter": {"optimizations": 20, "coach_chats": 1,  "coach_msgs": 15},
    "offer_mode": {"optimizations": 40, "coach_chats": 10, "coach_msgs": 20},
}


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


def limits_for(profile: dict) -> dict[str, int]:
    """Limits for the tier the user can currently use (honours cancellation grace)."""
    return TIER_LIMITS[effective_tier(profile)]


def optimization_limit(profile: dict) -> int:
    return limits_for(profile)["optimizations"]


def coach_chat_limit(profile: dict) -> int:
    return limits_for(profile)["coach_chats"]


def coach_msg_limit(profile: dict) -> int:
    return limits_for(profile)["coach_msgs"]


def has_feature_access(feature: Feature, profile: dict) -> bool:
    user_rank = TIER_RANK[effective_tier(profile)]
    needed_rank = TIER_RANK[FEATURE_MIN_TIER[feature]]
    return user_rank >= needed_rank
