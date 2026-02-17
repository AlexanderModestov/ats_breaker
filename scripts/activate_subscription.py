"""One-off script to find a completed Stripe checkout and activate the subscription in Supabase."""

import os
import sys
from datetime import datetime, timezone

# Load .env from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import stripe
from supabase import create_client

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def main():
    # List recent completed checkout sessions
    print("Fetching recent checkout sessions from Stripe...")
    sessions = stripe.checkout.Session.list(limit=10, status="complete")

    subscription_sessions = [
        s for s in sessions.data if s.mode == "subscription" and s.subscription
    ]

    if not subscription_sessions:
        print("No completed subscription checkout sessions found.")
        return

    print(f"\nFound {len(subscription_sessions)} completed subscription session(s):\n")
    for i, s in enumerate(subscription_sessions):
        user_id = s.metadata.get("user_id", "unknown")
        print(f"  [{i}] session={s.id}  user={user_id}  customer={s.customer}  created={datetime.fromtimestamp(s.created, tz=timezone.utc)}")

    choice = input(f"\nWhich session to activate? [0-{len(subscription_sessions)-1}]: ").strip()
    session = subscription_sessions[int(choice)]

    user_id = session.metadata.get("user_id")
    if not user_id:
        print("ERROR: No user_id in session metadata.")
        return

    # Get subscription details
    sub = stripe.Subscription.retrieve(session.subscription)
    print(f"\nSubscription object keys: {list(sub.keys())}")
    print(f"Subscription status: {sub.get('status')}")
    print(f"current_period_end: {sub.get('current_period_end')}")
    print(f"items: {sub.get('items')}")

    period_end_ts = sub.get("current_period_end")
    if not period_end_ts:
        # Try getting from the first item's period
        items = sub.get("items", {}).get("data", [])
        if items and items[0].get("current_period_end"):
            period_end_ts = items[0]["current_period_end"]
        else:
            print("\nERROR: Cannot find period end. Full subscription object:")
            print(dict(sub))
            return

    period_end = datetime.fromtimestamp(period_end_ts, tz=timezone.utc)

    print(f"\nActivating subscription for user {user_id}:")
    print(f"  subscription_id: {session.subscription}")
    print(f"  customer_id:     {session.customer}")
    print(f"  period_end:      {period_end.isoformat()}")

    confirm = input("\nProceed? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    # Update Supabase profile
    result = (
        supabase.table("profiles")
        .update({
            "subscription_status": "active",
            "subscription_id": session.subscription,
            "stripe_customer_id": session.customer,
            "current_period_end": period_end.isoformat(),
            "period_request_count": 0,
        })
        .eq("id", user_id)
        .execute()
    )

    if result.data:
        print(f"\nDone! Subscription activated for user {user_id}.")
    else:
        print(f"\nERROR: No profile found for user_id={user_id}")


if __name__ == "__main__":
    main()
