"""Tests for tier feature matrix, effective-tier logic, and per-tier limits."""

from datetime import datetime, timezone, timedelta

import pytest

from hr_breaker.services.tiers import (
    Feature,
    TIER_RANK,
    TIER_LIMITS,
    FEATURE_MIN_TIER,
    limits_for,
    optimization_limit,
    coach_chat_limit,
    coach_msg_limit,
    effective_tier,
    has_feature_access,
)


def _profile(**overrides) -> dict:
    base = {
        "subscription_tier": "free",
        "subscription_status": "none",
        "current_period_end": None,
        "period_request_count": 0,
    }
    base.update(overrides)
    return base


class TestTierRank:
    def test_ranks_are_strictly_increasing(self):
        assert TIER_RANK["free"] < TIER_RANK["job_hunter"] < TIER_RANK["offer_mode"]


class TestFeatureMatrix:
    def test_optimize_available_to_free(self):
        assert FEATURE_MIN_TIER[Feature.OPTIMIZE] == "free"

    def test_coach_open_to_free(self):
        # Tier gate passes everyone signed-in; quota check enforces the caps.
        assert FEATURE_MIN_TIER[Feature.COACH] == "free"


class TestEffectiveTier:
    def test_free_user_is_free(self):
        assert effective_tier(_profile()) == "free"

    def test_active_paying_user_returns_their_tier(self):
        p = _profile(subscription_tier="offer_mode", subscription_status="active")
        assert effective_tier(p) == "offer_mode"

    def test_cancelled_but_paid_through_keeps_tier(self):
        future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        p = _profile(
            subscription_tier="offer_mode",
            subscription_status="cancelled",
            current_period_end=future,
        )
        assert effective_tier(p) == "offer_mode"

    def test_cancelled_past_period_drops_to_free(self):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        p = _profile(
            subscription_tier="offer_mode",
            subscription_status="cancelled",
            current_period_end=past,
        )
        assert effective_tier(p) == "free"


class TestHasFeatureAccess:
    def test_free_can_optimize(self):
        assert has_feature_access(Feature.OPTIMIZE, _profile()) is True

    def test_free_can_coach(self):
        # Trial gate is on the quota check, not the tier matrix.
        assert has_feature_access(Feature.COACH, _profile()) is True

    def test_job_hunter_can_coach(self):
        p = _profile(subscription_tier="job_hunter", subscription_status="active")
        assert has_feature_access(Feature.COACH, p) is True

    def test_offer_mode_can_coach(self):
        p = _profile(subscription_tier="offer_mode", subscription_status="active")
        assert has_feature_access(Feature.COACH, p) is True


class TestTierLimits:
    def test_free_limits(self):
        assert TIER_LIMITS["free"] == {"optimizations": 3, "coach_chats": 1, "coach_msgs": 15}

    def test_job_hunter_limits(self):
        assert TIER_LIMITS["job_hunter"] == {"optimizations": 20, "coach_chats": 1, "coach_msgs": 15}

    def test_offer_mode_limits(self):
        assert TIER_LIMITS["offer_mode"] == {"optimizations": 40, "coach_chats": 10, "coach_msgs": 20}

    def test_limits_for_uses_effective_tier(self):
        # Cancelled-but-in-grace offer_mode still gets offer_mode limits.
        future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        p = _profile(subscription_tier="offer_mode", subscription_status="cancelled",
                     current_period_end=future)
        assert limits_for(p)["optimizations"] == 40

    def test_optimization_limit_helper(self):
        assert optimization_limit(_profile()) == 3

    def test_coach_chat_limit_helper(self):
        p = _profile(subscription_tier="offer_mode", subscription_status="active")
        assert coach_chat_limit(p) == 10

    def test_coach_msg_limit_helper(self):
        p = _profile(subscription_tier="offer_mode", subscription_status="active")
        assert coach_msg_limit(p) == 20
