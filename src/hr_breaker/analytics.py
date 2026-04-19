"""PostHog analytics integration."""

import os
from typing import Any

from posthog import Posthog

_client: Posthog | None = None


def get_posthog() -> Posthog | None:
    """Return the PostHog client, or None if not configured."""
    global _client
    if _client is not None:
        return _client

    api_key = os.getenv("POSTHOG_API_KEY", "")
    host = os.getenv("POSTHOG_HOST", "")
    if not api_key or not host:
        return None

    _client = Posthog(project_api_key=api_key, host=host)
    return _client


def capture(distinct_id: str, event: str, properties: dict[str, Any] | None = None) -> None:
    """Capture a PostHog event, silently ignoring errors."""
    client = get_posthog()
    if client is None:
        return
    try:
        client.capture(distinct_id, event, properties=properties or {})
    except Exception:
        pass


def shutdown() -> None:
    """Flush and shut down the PostHog client."""
    client = get_posthog()
    if client is not None:
        try:
            client.shutdown()
        except Exception:
            pass
