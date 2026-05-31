"""Stripe integration service for subscriptions and payments."""

import stripe
from datetime import datetime, timezone
from typing import Any

from hr_breaker.config import get_settings, logger


class StripeError(Exception):
    """Stripe operation error."""

    pass


class StripeService:
    """Service for Stripe operations."""

    def __init__(self):
        settings = get_settings()
        if not settings.stripe_secret_key:
            raise StripeError("Stripe secret key is required")
        stripe.api_key = settings.stripe_secret_key
        self._webhook_secret = settings.stripe_webhook_secret

    def _price_id_for_tier(self, tier: str) -> str:
        """Return the Stripe price ID for the given tier, or raise StripeError."""
        settings = get_settings()
        price_id = {
            "job_hunter": settings.stripe_price_job_hunter,
            "offer_mode": settings.stripe_price_offer_mode,
        }.get(tier)
        if not price_id:
            raise StripeError(f"Unknown tier: {tier}")
        return price_id

    def create_checkout_session_for_tier(
        self,
        *,
        tier: str,
        user_id: str,
        user_email: str,
        success_url: str,
        cancel_url: str,
        stripe_customer_id: str | None = None,
    ) -> str:
        """Create a subscription checkout session for the given tier."""
        price_id = self._price_id_for_tier(tier)

        try:
            session_params: dict[str, Any] = {
                "mode": "subscription",
                "line_items": [{"price": price_id, "quantity": 1}],
                "success_url": success_url,
                "cancel_url": cancel_url,
                "metadata": {"user_id": user_id, "tier": tier},
                "subscription_data": {"metadata": {"user_id": user_id, "tier": tier}},
            }
            if stripe_customer_id:
                session_params["customer"] = stripe_customer_id
            else:
                session_params["customer_email"] = user_email

            session = stripe.checkout.Session.create(**session_params)
            return session.url
        except stripe.StripeError as e:
            logger.error(f"Stripe checkout session creation failed: {e}")
            raise StripeError(f"Failed to create checkout session: {e}") from e

    def create_billing_portal_session(
        self,
        *,
        customer_id: str,
        return_url: str,
    ) -> str:
        """Create a Stripe Billing Portal session for self-service plan management."""
        try:
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )
            return session.url
        except stripe.StripeError as e:
            logger.error(f"Stripe billing portal session creation failed: {e}")
            raise StripeError(f"Failed to create billing portal session: {e}") from e

    def construct_webhook_event(self, payload: bytes, sig_header: str) -> stripe.Event:
        """
        Construct and verify a webhook event.

        Returns:
            The verified Stripe event
        """
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, self._webhook_secret
            )
            return event
        except stripe.SignatureVerificationError as e:
            logger.error(f"Stripe webhook signature verification failed: {e}")
            raise StripeError("Invalid webhook signature") from e
        except Exception as e:
            logger.error(f"Stripe webhook construction failed: {e}")
            raise StripeError(f"Failed to construct webhook event: {e}") from e

    def get_subscription(self, subscription_id: str) -> stripe.Subscription:
        """Get a subscription by ID."""
        try:
            return stripe.Subscription.retrieve(subscription_id)
        except stripe.StripeError as e:
            logger.error(f"Failed to retrieve subscription: {e}")
            raise StripeError(f"Failed to retrieve subscription: {e}") from e

    @staticmethod
    def get_period_end(subscription: stripe.Subscription) -> int:
        """
        Extract current_period_end from a subscription.

        Stripe moved this field from the subscription to subscription items.
        Falls back to items.data[0].current_period_end when top-level is absent.
        """
        top_level = subscription.get("current_period_end")
        if top_level:
            return top_level

        items = subscription.get("items", {}).get("data", [])
        if items:
            item_period = items[0].get("current_period_end")
            if item_period:
                return item_period

        raise StripeError(
            f"No current_period_end found on subscription {subscription.get('id')}"
        )

    @staticmethod
    def tier_from_subscription(subscription) -> str:
        """Read tier from price.metadata.tier on the first subscription item.

        Returns 'free' as a defensive default if metadata is missing or malformed.
        """
        sub_id = None
        try:
            sub_id = getattr(subscription, "id", None) or (
                subscription.get("id") if hasattr(subscription, "get") else None
            )
            sub_metadata = getattr(subscription, "metadata", None)
            sub_metadata_dict = dict(sub_metadata) if sub_metadata else None
            logger.info(
                f"[tier-debug] sub.id={sub_id} sub.metadata={sub_metadata_dict}"
            )

            items = subscription.get("items", {}).get("data", [])
            logger.info(f"[tier-debug] items_count={len(items)}")
            if not items:
                return "free"
            price = items[0].get("price", {})
            price_id = price.get("id", None) if isinstance(price, dict) else getattr(price, "id", None)
            price_type = type(price).__name__
            metadata = price.get("metadata", {}) if isinstance(price, dict) else getattr(price, "metadata", {}) or {}
            metadata_dict = dict(metadata) if metadata else None
            logger.info(
                f"[tier-debug] price.id={price_id} price_type={price_type} "
                f"price.metadata={metadata_dict}"
            )
            tier = metadata.get("tier") if isinstance(metadata, dict) else getattr(metadata, "tier", None)
            logger.info(f"[tier-debug] resolved tier from price.metadata={tier!r}")
            if tier in ("job_hunter", "offer_mode"):
                return tier
        except (KeyError, AttributeError, TypeError) as e:
            logger.warning(f"[tier-debug] parse error for sub {sub_id}: {e}")

        logger.warning(f"[tier-debug] falling back to 'free' for sub {sub_id}")
        return "free"

    def preview_upgrade(self, *, subscription_id: str, new_tier: str) -> dict:
        """Return the proration amount_due (cents) for switching to new_tier."""
        price_id = self._price_id_for_tier(new_tier)

        subscription = self.get_subscription(subscription_id)
        item_id = subscription["items"]["data"][0]["id"]
        customer_id = subscription["customer"]

        try:
            invoice = stripe.Invoice.create_preview(
                customer=customer_id,
                subscription=subscription_id,
                subscription_details={"items": [{"id": item_id, "price": price_id}]},
            )
            lines = invoice["lines"]["data"]
            # Proration lines start ~now; the next billing cycle's charge starts
            # at the period boundary (later timestamp). Exclude the next-cycle line
            # by filtering out lines that start latest among all lines.
            starts = [line.get("period", {}).get("start", 0) for line in lines]
            next_cycle_start = max(starts) if starts else 0
            min_start = min(starts) if starts else 0
            if next_cycle_start == min_start:
                proration_amount = sum(line["amount"] for line in lines)
            else:
                proration_amount = sum(
                    line["amount"]
                    for line in lines
                    if line.get("period", {}).get("start", 0) < next_cycle_start
                )
            return {"amount_due": proration_amount, "currency": invoice["currency"]}
        except stripe.StripeError as e:
            logger.error(f"Failed to preview upgrade: {e}")
            raise StripeError(f"Failed to preview upgrade: {e}") from e

    def upgrade_subscription(self, *, subscription_id: str, new_tier: str, user_id: str) -> None:
        """Upgrade to new_tier immediately; Stripe creates a proration invoice."""
        price_id = self._price_id_for_tier(new_tier)

        subscription = self.get_subscription(subscription_id)
        item_id = subscription["items"]["data"][0]["id"]

        try:
            stripe.Subscription.modify(
                subscription_id,
                items=[{"id": item_id, "price": price_id}],
                proration_behavior="always_invoice",
                metadata={"tier": new_tier, "user_id": user_id},
            )
        except stripe.StripeError as e:
            logger.error(f"Failed to upgrade subscription: {e}")
            raise StripeError(f"Failed to upgrade subscription: {e}") from e

    def retrieve_checkout_session(self, session_id: str) -> stripe.checkout.Session:
        """Retrieve a checkout session by ID."""
        try:
            return stripe.checkout.Session.retrieve(session_id)
        except stripe.StripeError as e:
            logger.error(f"Failed to retrieve checkout session: {e}")
            raise StripeError(f"Failed to retrieve checkout session: {e}") from e
