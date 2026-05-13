"""Tests for tier feature matrix and effective-tier logic."""

from datetime import datetime, timezone, timedelta

import pytest

from hr_breaker.services.tiers import (
    Feature,
    TIER_RANK,
    FEATURE_MIN_TIER,
    FREE_COACH_THREADS,
    FREE_COACH_TURNS,
    FREE_WEEKLY_LIMIT,
    coach_is_unlimited,
    effective_tier,
    has_feature_access,
    maybe_reset_weekly_window,
)


def _profile(**overrides) -> dict:
    base = {
        "subscription_tier": "free",
        "subscription_status": "none",
        "current_period_end": None,
        "period_request_count": 0,
        "weekly_reset_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
    }
    base.update(overrides)
    return base


class TestTierRank:
    def test_ranks_are_strictly_increasing(self):
        assert TIER_RANK["free"] < TIER_RANK["job_hunter"] < TIER_RANK["offer_mode"]


class TestFeatureMatrix:
    def test_optimize_available_to_free(self):
        assert FEATURE_MIN_TIER[Feature.OPTIMIZE] == "free"

    def test_coach_requires_offer_mode(self):
        assert FEATURE_MIN_TIER[Feature.COACH] == "offer_mode"


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

    def test_free_cannot_coach(self):
        assert has_feature_access(Feature.COACH, _profile()) is False

    def test_job_hunter_cannot_coach(self):
        p = _profile(subscription_tier="job_hunter", subscription_status="active")
        assert has_feature_access(Feature.COACH, p) is False

    def test_offer_mode_can_coach(self):
        p = _profile(subscription_tier="offer_mode", subscription_status="active")
        assert has_feature_access(Feature.COACH, p) is True


class TestCoachTrialConstants:
    def test_thread_limit_is_3(self):
        assert FREE_COACH_THREADS == 3

    def test_turn_limit_is_5(self):
        assert FREE_COACH_TURNS == 5


class TestCoachIsUnlimited:
    def test_free_is_not_unlimited(self):
        assert coach_is_unlimited(_profile()) is False

    def test_job_hunter_is_not_unlimited(self):
        p = _profile(subscription_tier="job_hunter", subscription_status="active")
        assert coach_is_unlimited(p) is False

    def test_offer_mode_active_is_unlimited(self):
        p = _profile(subscription_tier="offer_mode", subscription_status="active")
        assert coach_is_unlimited(p) is True

    def test_offer_mode_cancelled_within_grace_is_unlimited(self):
        future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        p = _profile(
            subscription_tier="offer_mode",
            subscription_status="cancelled",
            current_period_end=future,
        )
        assert coach_is_unlimited(p) is True

    def test_offer_mode_cancelled_after_grace_is_not_unlimited(self):
        past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        p = _profile(
            subscription_tier="offer_mode",
            subscription_status="cancelled",
            current_period_end=past,
        )
        assert coach_is_unlimited(p) is False


class TestWeeklyWindowReset:
    def test_does_not_reset_before_due(self):
        p = _profile(period_request_count=2)
        result = maybe_reset_weekly_window(p)
        assert result["period_request_count"] == 2

    def test_resets_after_due(self):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        p = _profile(period_request_count=3, weekly_reset_at=past)
        result = maybe_reset_weekly_window(p)
        assert result["period_request_count"] == 0
        new_reset = datetime.fromisoformat(result["weekly_reset_at"])
        assert new_reset > datetime.now(timezone.utc) + timedelta(days=6)
