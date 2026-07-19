"""Retry helper for transient model-provider errors (Vertex 429/503)."""

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic_ai.exceptions import ModelHTTPError

from hr_breaker.config import get_settings, logger

T = TypeVar("T")

# Vertex returns 429 RESOURCE_EXHAUSTED on quota / shared-capacity exhaustion and
# 503 UNAVAILABLE on transient overload. Both are explicitly retryable.
_RETRYABLE_STATUS = (429, 503)

# Process-wide cap on concurrent model calls so parallel requests don't stampede
# the shared Vertex quota. Created lazily so tests / CLI don't need an event
# loop at import time.
_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(get_settings().model_max_concurrency)
    return _semaphore


async def with_model_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    label: str = "model call",
    max_attempts: int = 4,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    timeout: float | None = None,
) -> T:
    """Run ``operation`` (an async model call), retrying transient Vertex errors
    with full-jitter exponential backoff.

    Each attempt is bounded by ``timeout`` seconds (default from settings) so a
    stalled connection can't hang the caller indefinitely, and all calls share
    a process-wide concurrency semaphore. Timeouts are retried like transient
    errors; non-transient errors and the final attempt re-raise immediately.
    """
    if timeout is None:
        timeout = get_settings().model_call_timeout
    for attempt in range(1, max_attempts + 1):
        try:
            async with _get_semaphore():
                return await asyncio.wait_for(operation(), timeout=timeout)
        except TimeoutError:
            if attempt == max_attempts:
                raise
            logger.warning(
                f"{label}: timed out after {timeout:.0f}s "
                f"(attempt {attempt}/{max_attempts}); retrying"
            )
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
