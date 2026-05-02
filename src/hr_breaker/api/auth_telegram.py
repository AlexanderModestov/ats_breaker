"""Telegram WebApp initData validation per the official spec.

https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl


class InitDataError(Exception):
    """Raised when initData is malformed, expired, or has an invalid signature."""


@dataclass
class ValidatedInitData:
    telegram_id: int


def parse_and_validate_init_data(
    init_data: str, bot_token: str, max_age_seconds: int
) -> ValidatedInitData:
    """Parse a Telegram WebApp initData query string and verify its HMAC.

    Raises ``InitDataError`` for any failure mode. On success returns the
    extracted Telegram user id.
    """
    pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))

    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise InitDataError("Missing hash")

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(pairs.items())
    )
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256
    ).digest()
    expected = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, received_hash):
        raise InitDataError("Invalid Telegram signature")

    auth_date_str = pairs.get("auth_date")
    if not auth_date_str:
        raise InitDataError("Missing auth_date")
    try:
        auth_date = int(auth_date_str)
    except ValueError as e:
        raise InitDataError("Invalid auth_date") from e

    if int(time.time()) - auth_date > max_age_seconds:
        raise InitDataError("initData expired")

    user_raw = pairs.get("user")
    if not user_raw:
        raise InitDataError("Missing user field")
    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError as e:
        raise InitDataError("Malformed user field") from e

    telegram_id = user.get("id")
    if not isinstance(telegram_id, int):
        raise InitDataError("Missing user.id")

    return ValidatedInitData(telegram_id=telegram_id)
