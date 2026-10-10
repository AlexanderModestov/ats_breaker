"""Retry helper for transient model-provider errors (429 / 5xx / connection / timeout)."""

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic_ai.exceptions import FallbackExceptionGroup, ModelAPIError, ModelHTTPError

from hr_breaker.config import get_settings, logger

T = TypeVar("T")

# Rate limit / quota (429), server errors (500/502/503/504) and provider overload
# (529, Anthropic). 400/401/403/404 are caller errors: retrying or switching
# provider will not fix them.
_RETRYABLE_STATUS = (429, 500, 502, 503, 504, 529)

# Process-wide cap on concurrent model calls so parallel requests don't stampede
# provider quotas. Created lazily so tests / CLI don't need an event loop at
# import time.
_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(get_settings().model_max_concurrency)
    return _semaphore


def is_transient_error(exc: BaseException) -> bool:
    """True if retrying (or falling back to another provider) can plausibly help."""
    if isinstance(exc, FallbackExceptionGroup):
        return all(is_transient_error(e) for e in exc.exceptions)
    if isinstance(exc, ModelHTTPError):
        return exc.status_code in _RETRYABLE_STATUS
    if isinstance(exc, ModelAPIError):  # non-HTTP: connection reset, DNS, etc.
        return True
    return isinstance(exc, TimeoutError)


async def with_model_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    label: str = "model call",
    max_attempts: int = 4,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    timeout: float | None = None,
) -> T:
    """Run ``operation`` (an async model call), retrying transient provider errors
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
        except (ModelAPIError, FallbackExceptionGroup) as e:
            if not is_transient_error(e) or attempt == max_attempts:
                raise
            cap = min(base_delay * 2 ** (attempt - 1), max_delay)
            delay = random.uniform(0, cap)
            logger.warning(
                f"{label}: transient error {type(e).__name__} "
                f"(attempt {attempt}/{max_attempts}); retrying in {delay:.1f}s"
            )
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover
