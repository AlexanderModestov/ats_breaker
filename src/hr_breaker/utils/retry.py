"""Retry helper for transient model-provider errors (Vertex 429/503)."""

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic_ai.exceptions import ModelHTTPError

from hr_breaker.config import logger

T = TypeVar("T")

# Vertex returns 429 RESOURCE_EXHAUSTED on quota / shared-capacity exhaustion and
# 503 UNAVAILABLE on transient overload. Both are explicitly retryable.
_RETRYABLE_STATUS = (429, 503)


async def with_model_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    label: str = "model call",
    max_attempts: int = 4,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> T:
    """Run ``operation`` (an async model call), retrying transient Vertex errors
    with full-jitter exponential backoff.

    Non-transient errors and the final attempt re-raise immediately.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            return await operation()
        except ModelHTTPError as e:
            if e.status_code not in _RETRYABLE_STATUS or attempt == max_attempts:
                raise
            cap = min(base_delay * 2 ** (attempt - 1), max_delay)
            delay = random.uniform(0, cap)
            logger.warning(
                f"{label}: transient {e.status_code} (attempt {attempt}/{max_attempts}); "
                f"retrying in {delay:.1f}s"
            )
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover
