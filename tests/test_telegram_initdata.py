"""Tests for Telegram WebApp initData validation."""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from hr_breaker.api.auth_telegram import (
    InitDataError,
    parse_and_validate_init_data,
)

BOT_TOKEN = "test-bot-token-1234567890"


def _sign(params: dict) -> str:
    """Build a Telegram-signed initData query string for tests."""
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(params.items())
    )
    secret_key = hmac.new(
        b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256
    ).digest()
    h = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    return urlencode({**params, "hash": h})


def test_valid_init_data_returns_telegram_id():
    user = json.dumps({"id": 12345, "first_name": "Test"})
    init_data = _sign({"auth_date": str(int(time.time())), "user": user})

    result = parse_and_validate_init_data(init_data, BOT_TOKEN, max_age_seconds=3600)

    assert result.telegram_id == 12345


def test_invalid_hash_raises():
    user = json.dumps({"id": 12345})
    init_data = _sign({"auth_date": str(int(time.time())), "user": user})
    tampered = init_data.replace("12345", "99999")

    with pytest.raises(InitDataError, match="signature"):
        parse_and_validate_init_data(tampered, BOT_TOKEN, max_age_seconds=3600)


def test_expired_init_data_raises():
    user = json.dumps({"id": 12345})
    old_ts = str(int(time.time()) - 7200)  # 2h ago
    init_data = _sign({"auth_date": old_ts, "user": user})

    with pytest.raises(InitDataError, match="expired"):
        parse_and_validate_init_data(init_data, BOT_TOKEN, max_age_seconds=3600)


def test_missing_hash_raises():
    init_data = urlencode({"auth_date": str(int(time.time())), "user": "{}"})

    with pytest.raises(InitDataError, match="hash"):
        parse_and_validate_init_data(init_data, BOT_TOKEN, max_age_seconds=3600)


def test_missing_user_raises():
    init_data = _sign({"auth_date": str(int(time.time()))})

    with pytest.raises(InitDataError, match="user"):
        parse_and_validate_init_data(init_data, BOT_TOKEN, max_age_seconds=3600)
