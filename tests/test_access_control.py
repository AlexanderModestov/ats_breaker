"""Tests for tier-aware access control."""

from unittest.mock import patch

from hr_breaker.services.access_control import (
    AccessResult,
    check_feature_access,
    check_optimization_quota,
)
from hr_breaker.services.tiers import Feature


def _profile(**overrides) -> dict:
    base = {
        "subscription_tier": "free",
        "subscription_status": "none",
        "current_period_end": None,
        "period_request_count": 0,
    }
    base.update(overrides)
    return base


class TestUnlimitedAdmin:
    def test_admin_bypasses_feature_check(self):
        with patch("hr_breaker.services.access_control.get_settings") as mock:
            mock.return_value.unlimited_users = ["admin@test.com"]
            r = check_feature_access(Feature.COACH, "admin@test.com", _profile())
        assert r.allowed


class TestFeatureAccess:
    def _no_unlimited(self):
        m = patch("hr_breaker.services.access_control.get_settings")
        mock = m.start()
        mock.return_value.unlimited_users = []
        return m

    def test_free_allowed_coach_via_trial(self):
        # Tier matrix is open; quota check enforces trial caps separately.
        m = self._no_unlimited()
        r = check_feature_access(Feature.COACH, "u@test.com", _profile())
        m.stop()
        assert r.allowed is True

    def test_offer_mode_allowed_coach(self):
        m = self._no_unlimited()
        p = _profile(subscription_tier="offer_mode", subscription_status="active")
        r = check_feature_access(Feature.COACH, "u@test.com", p)
        m.stop()
        assert r.allowed is True


def _p(tier="free", status="none", used=0, period_end=None):
    return {
        "subscription_tier": tier, "subscription_status": status,
        "current_period_end": period_end, "period_request_count": used,
    }


class TestOptimizationQuota:
    def test_free_under_limit(self):
        r = check_optimization_quota("u@x.com", _p(used=1))
        assert r.allowed and r.remaining == 2

    def test_free_at_limit_blocked(self):
        r = check_optimization_quota("u@x.com", _p(used=3))
        assert not r.allowed and r.remaining == 0 and r.reason == "quota_exhausted"

    def test_free_renewal_date_is_none(self):
        r = check_optimization_quota("u@x.com", _p(used=3))
        assert r.renewal_date is None  # Free never resets

    def test_job_hunter_metered(self):
        r = check_optimization_quota("u@x.com", _p(tier="job_hunter", status="active", used=19))
        assert r.allowed and r.remaining == 1

    def test_job_hunter_at_limit_blocked_with_renewal(self):
        end = "2099-01-01T00:00:00+00:00"
        r = check_optimization_quota("u@x.com", _p(tier="job_hunter", status="active", used=20, period_end=end))
        assert not r.allowed and r.renewal_date is not None

    def test_admin_allowlist_bypasses(self, monkeypatch):
        from hr_breaker.services import access_control
        monkeypatch.setattr(access_control, "_is_unlimited", lambda e: True)
        r = check_optimization_quota("admin@x.com", _p(used=999))
        assert r.allowed
