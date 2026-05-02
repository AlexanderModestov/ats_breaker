"""Tests for POST /api/auth/telegram/exchange."""

import hashlib
import hmac
import json
import time
from unittest.mock import MagicMock, patch
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from hr_breaker.api.main import app
from hr_breaker.api.deps import get_supabase_service

BOT_TOKEN = "test-bot-token-1234567890"


def _sign(params: dict, token: str = BOT_TOKEN) -> str:
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(params.items())
    )
    secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**params, "hash": h})


@pytest.fixture
def fake_supabase():
    svc = MagicMock()
    return svc


@pytest.fixture
def client(fake_supabase):
    app.dependency_overrides[get_supabase_service] = lambda: fake_supabase
    with patch("hr_breaker.api.routes.telegram.get_settings") as mock_settings:
        mock_settings.return_value.telegram_bot_token = BOT_TOKEN
        yield TestClient(app)
    app.dependency_overrides.clear()


def _valid_init_data(telegram_id: int = 12345) -> str:
    return _sign({
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": telegram_id, "first_name": "T"}),
    })


def test_exchange_success_returns_token_hash(client, fake_supabase):
    fake_supabase.get_profile_by_telegram_id.return_value = {
        "id": "user-uuid",
        "email": "user@example.com",
    }
    fake_supabase.generate_magiclink.return_value = "tok_abc"

    r = client.post(
        "/api/auth/telegram/exchange",
        json={"init_data": _valid_init_data()},
    )

    assert r.status_code == 200
    assert r.json() == {"token_hash": "tok_abc", "email": "user@example.com"}
    fake_supabase.generate_magiclink.assert_called_once_with("user@example.com")


def test_exchange_invalid_signature_returns_401(client):
    bad = _sign({"auth_date": str(int(time.time())), "user": "{}"}, token="WRONG")
    r = client.post("/api/auth/telegram/exchange", json={"init_data": bad})
    assert r.status_code == 401


def test_exchange_expired_returns_401(client):
    expired = _sign({
        "auth_date": str(int(time.time()) - 7200),
        "user": json.dumps({"id": 1}),
    })
    r = client.post("/api/auth/telegram/exchange", json={"init_data": expired})
    assert r.status_code == 401


def test_exchange_unlinked_returns_404(client, fake_supabase):
    fake_supabase.get_profile_by_telegram_id.return_value = None
    r = client.post(
        "/api/auth/telegram/exchange",
        json={"init_data": _valid_init_data()},
    )
    assert r.status_code == 404


def test_exchange_no_email_returns_409(client, fake_supabase):
    fake_supabase.get_profile_by_telegram_id.return_value = {
        "id": "user-uuid",
        "email": None,
    }
    r = client.post(
        "/api/auth/telegram/exchange",
        json={"init_data": _valid_init_data()},
    )
    assert r.status_code == 409
