"""Tests for tier-aware access control."""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from hr_breaker.services.access_control import (
    AccessResult,
    check_feature_access,
    check_quota,
    consume_request,
)
from hr_breaker.services.tiers import Feature, FREE_WEEKLY_LIMIT


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


class TestUnlimitedAdmin:
    def test_admin_bypasses_feature_check(self):
        with patch("hr_breaker.services.access_control.get_settings") as mock:
            mock.return_value.unlimited_users = ["admin@test.com"]
            r = check_feature_access(Feature.COACH, "admin@test.com", _profile())
        assert r.allowed and r.unlimited

    def test_admin_bypasses_quota(self):
        with patch("hr_breaker.services.access_control.get_settings") as mock:
            mock.return_value.unlimited_users = ["admin@test.com"]
            r = check_quota("admin@test.com", _profile(period_request_count=999))
        assert r.allowed and r.unlimited


class TestFeatureAccess:
    def _no_unlimited(self):
        m = patch("hr_breaker.services.access_control.get_settings")
        mock = m.start()
        mock.return_value.unlimited_users = []
        return m

    def test_free_blocked_from_coach(self):
        m = self._no_unlimited()
        r = check_feature_access(Feature.COACH, "u@test.com", _profile())
        m.stop()
        assert r.allowed is False
        assert r.reason == "feature_locked"
        assert r.required_tier == "offer_mode"

    def test_offer_mode_allowed_coach(self):
        m = self._no_unlimited()
        p = _profile(subscription_tier="offer_mode", subscription_status="active")
        r = check_feature_access(Feature.COACH, "u@test.com", p)
        m.stop()
        assert r.allowed is True


class TestQuota:
    def _no_unlimited(self):
        m = patch("hr_breaker.services.access_control.get_settings")
        mock = m.start()
        mock.return_value.unlimited_users = []
        return m

    def test_free_with_remaining(self):
        m = self._no_unlimited()
        p = _profile(period_request_count=1)
        r = check_quota("u@test.com", p)
        m.stop()
        assert r.allowed is True
        assert r.remaining == FREE_WEEKLY_LIMIT - 1

    def test_free_quota_exhausted(self):
        m = self._no_unlimited()
        p = _profile(period_request_count=FREE_WEEKLY_LIMIT)
        r = check_quota("u@test.com", p)
        m.stop()
        assert r.allowed is False
        assert r.reason == "quota_exhausted"
        assert r.renewal_date is not None

    def test_paid_user_unlimited(self):
        m = self._no_unlimited()
        p = _profile(subscription_tier="job_hunter", subscription_status="active",
                     period_request_count=999)
        r = check_quota("u@test.com", p)
        m.stop()
        assert r.allowed is True and r.unlimited

    def test_lazy_reset_when_window_expired(self):
        m = self._no_unlimited()
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        p = _profile(period_request_count=FREE_WEEKLY_LIMIT, weekly_reset_at=past)
        r = check_quota("u@test.com", p)
        m.stop()
        assert r.allowed is True
        assert r.remaining == FREE_WEEKLY_LIMIT  # full quota after reset


class TestConsumeRequest:
    def test_free_user_increments_period_counter(self):
        with patch("hr_breaker.services.access_control.get_settings") as mock:
            mock.return_value.unlimited_users = []
            updates = consume_request("u@test.com", _profile(period_request_count=0))
        assert updates["period_request_count"] == 1

    def test_paid_user_no_increment(self):
        with patch("hr_breaker.services.access_control.get_settings") as mock:
            mock.return_value.unlimited_users = []
            p = _profile(subscription_tier="offer_mode", subscription_status="active")
            updates = consume_request("u@test.com", p)
        assert updates == {}

    def test_admin_no_increment(self):
        with patch("hr_breaker.services.access_control.get_settings") as mock:
            mock.return_value.unlimited_users = ["a@test.com"]
            updates = consume_request("a@test.com", _profile())
        assert updates == {}
