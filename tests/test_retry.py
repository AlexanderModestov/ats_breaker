"""Tests for the model-call retry helper."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai.exceptions import ModelHTTPError

import hr_breaker.utils.retry as retry_mod
from hr_breaker.utils.retry import with_model_retry


def _err(status: int) -> ModelHTTPError:
    return ModelHTTPError(status_code=status, model_name="test-model", body=None)


async def test_returns_result_without_retry_on_success():
    calls = 0

    async def op():
        nonlocal calls
        calls += 1
        return "ok"

    assert await with_model_retry(op) == "ok"
    assert calls == 1


async def test_retries_on_429_then_succeeds():
    calls = 0

    async def op():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise _err(429)
        return "ok"

    with patch("hr_breaker.utils.retry.asyncio.sleep", new=AsyncMock()) as slept:
        result = await with_model_retry(op, max_attempts=4, base_delay=0.01)

    assert result == "ok"
    assert calls == 3
    assert slept.await_count == 2


async def test_does_not_retry_non_transient_status():
    calls = 0

    async def op():
        nonlocal calls
        calls += 1
        raise _err(400)

    with patch("hr_breaker.utils.retry.asyncio.sleep", new=AsyncMock()) as slept:
        with pytest.raises(ModelHTTPError):
            await with_model_retry(op)

    assert calls == 1
    assert slept.await_count == 0


async def test_reraises_after_exhausting_attempts():
    calls = 0

    async def op():
        nonlocal calls
        calls += 1
        raise _err(429)

    with patch("hr_breaker.utils.retry.asyncio.sleep", new=AsyncMock()) as slept:
        with pytest.raises(ModelHTTPError):
            await with_model_retry(op, max_attempts=3, base_delay=0.01)

    assert calls == 3
    assert slept.await_count == 2


async def test_hung_call_times_out_and_retries():
    calls = 0

    async def op():
        nonlocal calls
        calls += 1
        if calls == 1:
            await asyncio.sleep(60)  # simulate a stalled connection
        return "ok"

    assert await with_model_retry(op, timeout=0.05) == "ok"
    assert calls == 2


async def test_timeout_reraises_after_exhausting_attempts():
    async def op():
        await asyncio.sleep(60)

    with pytest.raises(TimeoutError):
        await with_model_retry(op, max_attempts=2, timeout=0.05)


async def test_semaphore_caps_concurrency(monkeypatch):
    monkeypatch.setattr(retry_mod, "_semaphore", asyncio.Semaphore(2))
    active = 0
    peak = 0

    async def op():
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return "ok"

    results = await asyncio.gather(*(with_model_retry(op, timeout=5) for _ in range(6)))
    assert results == ["ok"] * 6
    assert peak <= 2


from pydantic_ai.exceptions import FallbackExceptionGroup, ModelAPIError

from hr_breaker.utils.retry import is_transient_error


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504, 529])
def test_transient_http_statuses(status):
    assert is_transient_error(_err(status)) is True


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_non_transient_http_statuses(status):
    assert is_transient_error(_err(status)) is False


def test_connection_error_is_transient():
    assert is_transient_error(ModelAPIError(model_name="m", message="connection reset")) is True


def test_timeout_is_transient():
    assert is_transient_error(TimeoutError()) is True


def test_unrelated_exception_is_not_transient():
    assert is_transient_error(ValueError("bad")) is False


def test_fallback_group_transient_only_if_all_inner_are():
    assert is_transient_error(FallbackExceptionGroup("x", [_err(429), _err(503)])) is True
    assert is_transient_error(FallbackExceptionGroup("x", [_err(429), _err(401)])) is False


async def test_retries_529_overloaded():
    calls = 0

    async def op():
        nonlocal calls
        calls += 1
        if calls < 2:
            raise _err(529)
        return "ok"

    with patch("hr_breaker.utils.retry.asyncio.sleep", new=AsyncMock()):
        assert await with_model_retry(op, base_delay=0.01) == "ok"
    assert calls == 2


async def test_retries_when_whole_fallback_chain_failed_transiently():
    calls = 0

    async def op():
        nonlocal calls
        calls += 1
        if calls < 2:
            raise FallbackExceptionGroup("all failed", [_err(429), _err(503)])
        return "ok"

    with patch("hr_breaker.utils.retry.asyncio.sleep", new=AsyncMock()):
        assert await with_model_retry(op, base_delay=0.01) == "ok"
    assert calls == 2


async def test_does_not_retry_fallback_group_with_non_transient_member():
    calls = 0

    async def op():
        nonlocal calls
        calls += 1
        raise FallbackExceptionGroup("all failed", [_err(429), _err(401)])

    with patch("hr_breaker.utils.retry.asyncio.sleep", new=AsyncMock()):
        with pytest.raises(FallbackExceptionGroup):
            await with_model_retry(op)
    assert calls == 1


import httpx


def test_raw_httpx_transport_errors_are_transient():
    assert is_transient_error(httpx.ReadTimeout("slow")) is True
    assert is_transient_error(httpx.ConnectTimeout("slow")) is True
    assert is_transient_error(httpx.ConnectError("refused")) is True
    assert is_transient_error(httpx.RemoteProtocolError("reset")) is True


@pytest.mark.parametrize(
    "exc",
    [httpx.ReadTimeout("slow"), httpx.ConnectError("refused"),
     ModelAPIError(model_name="m", message="connection reset")],
)
async def test_retries_raw_transport_and_non_http_api_errors(exc):
    calls = 0

    async def op():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise exc
        return "ok"

    with patch("hr_breaker.utils.retry.asyncio.sleep", new=AsyncMock()):
        assert await with_model_retry(op, base_delay=0.01) == "ok"
    assert calls == 2


async def test_retry_warning_includes_status_code(caplog):
    calls = 0

    async def op():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise _err(503)
        return "ok"

    from hr_breaker.config import logger

    logger.addHandler(caplog.handler)
    try:
        with patch("hr_breaker.utils.retry.asyncio.sleep", new=AsyncMock()):
            await with_model_retry(op)
    finally:
        logger.removeHandler(caplog.handler)
    assert any("503" in r.getMessage() for r in caplog.records)
