"""Tests for Telegram WebApp initData validation."""

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl, urlencode

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
    # Parse, flip a byte of the signed hash, re-encode — guarantees hash mismatch.
    pairs = dict(parse_qsl(init_data))
    pairs["hash"] = "0" * 64 if pairs["hash"][0] != "0" else "f" * 64
    tampered = urlencode(pairs)

    with pytest.raises(InitDataError, match="signature"):
        parse_and_validate_init_data(tampered, BOT_TOKEN, max_age_seconds=3600)


def test_tampered_auth_date_fails_with_signature_error_not_expired():
    """Hash check must run first: tampering auth_date should surface as a
    signature error, not an 'expired' error (otherwise the validator leaks
    information about which fields are checked)."""
    user = json.dumps({"id": 12345})
    init_data = _sign({"auth_date": str(int(time.time())), "user": user})
    pairs = dict(parse_qsl(init_data))
    pairs["auth_date"] = str(int(time.time()) - 7200)  # rewrite to "expired"
    tampered = urlencode(pairs)

    # The hash was computed against the original auth_date, so the signature
    # is now invalid. Validator must report "signature", not "expired".
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
