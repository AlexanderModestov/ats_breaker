"""Test the require_feature FastAPI dependency."""

from unittest.mock import patch, MagicMock

import pytest
from fastapi import HTTPException

from hr_breaker.api.deps import require_feature
from hr_breaker.services.tiers import Feature


def _profile(**o):
    base = {
        "subscription_tier": "free",
        "subscription_status": "none",
        "current_period_end": None,
        "period_request_count": 0,
        "weekly_reset_at": "2099-01-01T00:00:00+00:00",
    }
    base.update(o)
    return base


class TestRequireFeature:
    def test_allows_offer_mode_user_to_coach(self):
        with patch("hr_breaker.services.access_control.get_settings") as s:
            s.return_value.unlimited_users = []
            supabase = MagicMock()
            supabase.get_profile.return_value = _profile(
                subscription_tier="offer_mode", subscription_status="active"
            )
            dep = require_feature(Feature.COACH)
            result = dep(user=("uid", "u@test.com"), supabase=supabase)
            assert result == ("uid", "u@test.com")

    def test_blocks_free_user_from_coach_with_402(self):
        with patch("hr_breaker.services.access_control.get_settings") as s:
            s.return_value.unlimited_users = []
            supabase = MagicMock()
            supabase.get_profile.return_value = _profile()
            dep = require_feature(Feature.COACH)
            with pytest.raises(HTTPException) as exc:
                dep(user=("uid", "u@test.com"), supabase=supabase)
            assert exc.value.status_code == 402
            assert exc.value.detail["reason"] == "feature_locked"
            assert exc.value.detail["required_tier"] == "offer_mode"

    def test_returns_404_when_profile_missing(self):
        with patch("hr_breaker.services.access_control.get_settings") as s:
            s.return_value.unlimited_users = []
            supabase = MagicMock()
            supabase.get_profile.return_value = None
            dep = require_feature(Feature.COACH)
            with pytest.raises(HTTPException) as exc:
                dep(user=("uid", "u@test.com"), supabase=supabase)
            assert exc.value.status_code == 404
