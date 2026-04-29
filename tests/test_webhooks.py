"""Tests for the tier-aware Stripe webhook handler."""

from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from hr_breaker.api.routes.webhooks import handle_stripe_webhook


def _future_ts(days: int = 30) -> int:
    return int((datetime.now(timezone.utc) + timedelta(days=days)).timestamp())


def _event(event_type: str, data_object) -> SimpleNamespace:
    return SimpleNamespace(
        type=event_type,
        id="evt_test",
        data=SimpleNamespace(object=data_object),
    )


def _sub_object_dict(*, user_id="user-1", tier="offer_mode", status="active",
                     cancel_at_period_end=False, period_end_days=30):
    """Subscription object as Stripe SDK returns it (object-shaped for top-level, dict-shaped for items)."""
    obj = SimpleNamespace(
        metadata={"user_id": user_id},
        status=status,
        cancel_at_period_end=cancel_at_period_end,
        current_period_end=_future_ts(period_end_days),
    )
    return obj


def _retrieved_subscription(tier="offer_mode", period_end_days=30):
    """What StripeService.get_subscription returns: a dict-like with items.data[0].price.metadata.tier."""
    return {
        "items": {
            "data": [{"price": {"metadata": {"tier": tier}}, "current_period_end": _future_ts(period_end_days)}]
        },
        "current_period_end": _future_ts(period_end_days),
    }


@pytest.fixture
def mock_supabase():
    with patch("hr_breaker.api.routes.webhooks.SupabaseService") as cls:
        instance = MagicMock()
        cls.return_value = instance
        yield instance


@pytest.fixture
def mock_stripe():
    with patch("hr_breaker.api.routes.webhooks.StripeService") as cls:
        instance = MagicMock()
        # Static method must still be callable on the instance for these tests
        instance.tier_from_subscription = MagicMock(side_effect=lambda sub: sub["items"]["data"][0]["price"]["metadata"]["tier"])
        instance.get_period_end = MagicMock(side_effect=lambda sub: sub["current_period_end"])
        cls.return_value = instance
        yield instance


@pytest.fixture
def request_with_payload():
    request = AsyncMock()
    request.body.return_value = b"payload"
    return request


class TestCheckoutCompleted:
    @pytest.mark.asyncio
    async def test_sets_tier_active_and_period_end(self, mock_supabase, mock_stripe, request_with_payload):
        session = SimpleNamespace(
            metadata={"user_id": "user-1"},
            mode="subscription",
            subscription="sub_abc",
            customer="cus_xyz",
        )
        mock_stripe.construct_webhook_event.return_value = _event("checkout.session.completed", session)
        mock_stripe.get_subscription.return_value = _retrieved_subscription(tier="offer_mode")

        result = await handle_stripe_webhook(request_with_payload, "sig")

        assert result == {"status": "ok"}
        mock_supabase.update_profile.assert_called_once()
        args, _ = mock_supabase.update_profile.call_args
        user_id, updates = args
        assert user_id == "user-1"
        assert updates["subscription_tier"] == "offer_mode"
        assert updates["subscription_status"] == "active"
        assert updates["subscription_id"] == "sub_abc"
        assert updates["stripe_customer_id"] == "cus_xyz"
        assert "current_period_end" in updates

    @pytest.mark.asyncio
    async def test_ignores_non_subscription_mode(self, mock_supabase, mock_stripe, request_with_payload):
        session = SimpleNamespace(metadata={"user_id": "u"}, mode="payment", subscription=None, customer=None)
        mock_stripe.construct_webhook_event.return_value = _event("checkout.session.completed", session)

        result = await handle_stripe_webhook(request_with_payload, "sig")

        assert result == {"status": "ok"}
        mock_supabase.update_profile.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_missing_user_id(self, mock_supabase, mock_stripe, request_with_payload):
        session = SimpleNamespace(metadata=None, mode="subscription", subscription="sub", customer="c")
        mock_stripe.construct_webhook_event.return_value = _event("checkout.session.completed", session)

        result = await handle_stripe_webhook(request_with_payload, "sig")

        assert result == {"status": "ok"}
        mock_supabase.update_profile.assert_not_called()


class TestSubscriptionUpdated:
    @pytest.mark.asyncio
    async def test_active_renewal_keeps_tier(self, mock_supabase, mock_stripe, request_with_payload):
        sub = _sub_object_dict(tier="job_hunter", status="active", cancel_at_period_end=False)
        sub.items = {"data": [{"price": {"metadata": {"tier": "job_hunter"}}, "current_period_end": _future_ts(30)}]}
        mock_stripe.construct_webhook_event.return_value = _event("customer.subscription.updated", sub)
        mock_stripe.tier_from_subscription.side_effect = None
        mock_stripe.tier_from_subscription.return_value = "job_hunter"
        mock_stripe.get_period_end.side_effect = None
        mock_stripe.get_period_end.return_value = _future_ts(30)

        await handle_stripe_webhook(request_with_payload, "sig")

        args, _ = mock_supabase.update_profile.call_args
        _, updates = args
        assert updates["subscription_tier"] == "job_hunter"
        assert updates["subscription_status"] == "active"

    @pytest.mark.asyncio
    async def test_cancel_at_period_end_marks_cancelled(self, mock_supabase, mock_stripe, request_with_payload):
        sub = _sub_object_dict(tier="offer_mode", cancel_at_period_end=True)
        sub.items = {"data": [{"price": {"metadata": {"tier": "offer_mode"}}, "current_period_end": _future_ts(30)}]}
        mock_stripe.construct_webhook_event.return_value = _event("customer.subscription.updated", sub)
        mock_stripe.tier_from_subscription.side_effect = None
        mock_stripe.tier_from_subscription.return_value = "offer_mode"
        mock_stripe.get_period_end.side_effect = None
        mock_stripe.get_period_end.return_value = _future_ts(30)

        await handle_stripe_webhook(request_with_payload, "sig")

        args, _ = mock_supabase.update_profile.call_args
        _, updates = args
        assert updates["subscription_tier"] == "offer_mode"  # tier preserved during grace
        assert updates["subscription_status"] == "cancelled"


class TestSubscriptionDeleted:
    @pytest.mark.asyncio
    async def test_resets_to_free_and_clears_window(self, mock_supabase, mock_stripe, request_with_payload):
        sub = SimpleNamespace(metadata={"user_id": "u"})
        mock_stripe.construct_webhook_event.return_value = _event("customer.subscription.deleted", sub)

        await handle_stripe_webhook(request_with_payload, "sig")

        args, _ = mock_supabase.update_profile.call_args
        user_id, updates = args
        assert user_id == "u"
        assert updates["subscription_tier"] == "free"
        assert updates["subscription_status"] == "none"
        assert updates["subscription_id"] is None
        assert updates["current_period_end"] is None
        assert updates["period_request_count"] == 0
        assert "weekly_reset_at" in updates


class TestPaymentFailed:
    @pytest.mark.asyncio
    async def test_payment_failed_does_not_block(self, mock_supabase, mock_stripe, request_with_payload):
        invoice = SimpleNamespace()
        mock_stripe.construct_webhook_event.return_value = _event("invoice.payment_failed", invoice)

        result = await handle_stripe_webhook(request_with_payload, "sig")

        assert result == {"status": "ok"}
        mock_supabase.update_profile.assert_not_called()


class TestTierFromSubscription:
    """Direct tests for the helper, since webhook tests mock it."""

    def test_resolves_tier_from_metadata(self):
        from hr_breaker.services.stripe_service import StripeService
        sub = {"items": {"data": [{"price": {"metadata": {"tier": "offer_mode"}}}]}}
        assert StripeService.tier_from_subscription(sub) == "offer_mode"

    def test_unknown_tier_falls_back_to_free(self):
        from hr_breaker.services.stripe_service import StripeService
        sub = {"items": {"data": [{"price": {"metadata": {"tier": "enterprise"}}}]}}
        assert StripeService.tier_from_subscription(sub) == "free"

    def test_missing_metadata_falls_back_to_free(self):
        from hr_breaker.services.stripe_service import StripeService
        sub = {"items": {"data": [{"price": {}}]}}
        assert StripeService.tier_from_subscription(sub) == "free"

    def test_no_items_falls_back_to_free(self):
        from hr_breaker.services.stripe_service import StripeService
        sub = {"items": {"data": []}}
        assert StripeService.tier_from_subscription(sub) == "free"
