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
        settings = get_settings()
        price_id = {
            "job_hunter": settings.stripe_price_job_hunter,
            "offer_mode": settings.stripe_price_offer_mode,
        }.get(tier)
        if not price_id:
            raise StripeError(f"Unknown tier: {tier}")

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
        try:
            items = subscription.get("items", {}).get("data", [])
            if not items:
                return "free"
            price = items[0].get("price", {})
            metadata = price.get("metadata", {}) if isinstance(price, dict) else getattr(price, "metadata", {}) or {}
            tier = metadata.get("tier") if isinstance(metadata, dict) else getattr(metadata, "tier", None)
            if tier in ("job_hunter", "offer_mode"):
                return tier
        except (KeyError, AttributeError, TypeError):
            pass
        return "free"

    def retrieve_checkout_session(self, session_id: str) -> stripe.checkout.Session:
        """Retrieve a checkout session by ID."""
        try:
            return stripe.checkout.Session.retrieve(session_id)
        except stripe.StripeError as e:
            logger.error(f"Failed to retrieve checkout session: {e}")
            raise StripeError(f"Failed to retrieve checkout session: {e}") from e
