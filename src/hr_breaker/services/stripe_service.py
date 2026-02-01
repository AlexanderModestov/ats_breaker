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

    def create_checkout_session_subscription(
        self,
        user_id: str,
        user_email: str,
        success_url: str,
        cancel_url: str,
        stripe_customer_id: str | None = None,
    ) -> str:
        """
        Create a Stripe checkout session for subscription.

        Returns:
            The checkout session URL
        """
        settings = get_settings()

        try:
            session_params: dict[str, Any] = {
                "mode": "subscription",
                "line_items": [
                    {
                        "price": settings.stripe_price_id_subscription,
                        "quantity": 1,
                    }
                ],
                "success_url": success_url,
                "cancel_url": cancel_url,
                "metadata": {"user_id": user_id},
                "subscription_data": {"metadata": {"user_id": user_id}},
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

    def create_checkout_session_addon(
        self,
        user_id: str,
        stripe_customer_id: str,
        success_url: str,
        cancel_url: str,
    ) -> str:
        """
        Create a Stripe checkout session for add-on pack.

        Returns:
            The checkout session URL
        """
        settings = get_settings()

        if not stripe_customer_id:
            raise StripeError("Customer ID required for add-on purchase")

        try:
            session = stripe.checkout.Session.create(
                mode="payment",
                customer=stripe_customer_id,
                line_items=[
                    {
                        "price": settings.stripe_price_id_addon,
                        "quantity": 1,
                    }
                ],
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={"user_id": user_id, "type": "addon"},
            )
            return session.url

        except stripe.StripeError as e:
            logger.error(f"Stripe addon checkout session creation failed: {e}")
            raise StripeError(f"Failed to create checkout session: {e}") from e

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
