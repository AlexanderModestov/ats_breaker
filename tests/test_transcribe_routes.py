"""Tests for POST /api/coach/transcribe."""

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from hr_breaker.api.deps import (
    get_current_user,
    get_current_user_email,
    get_supabase_service,
)
from hr_breaker.api.main import app
from hr_breaker.services.transcriber import (
    EmptyTranscriptError,
    ProviderTranscriptionError,
)
from hr_breaker.services.voice_rate_limit import VoiceRateLimiter
from hr_breaker.api.routes.transcribe import get_voice_rate_limiter

USER = "user-uuid"
EMAIL = "user@example.com"


def _offer_mode_profile() -> dict:
    return {
        "id": USER,
        "subscription_tier": "offer_mode",
        "subscription_status": "active",
        "current_period_end": "2099-01-01T00:00:00+00:00",
        "period_request_count": 0,
        "weekly_reset_at": "2099-01-01T00:00:00+00:00",
    }


@pytest.fixture
def fake_supabase():
    svc = MagicMock()
    svc.get_profile.return_value = _offer_mode_profile()
    return svc


@pytest.fixture
def client(fake_supabase):
    app.dependency_overrides[get_supabase_service] = lambda: fake_supabase
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_current_user_email] = lambda: (USER, EMAIL)
    # Fresh limiter per test, but a single instance per fixture so state accumulates across
    # requests in the same test (the lambda would otherwise be invoked per request).
    _limiter = VoiceRateLimiter(max_per_window=2, window_seconds=3600)
    app.dependency_overrides[get_voice_rate_limiter] = lambda: _limiter
    with patch("hr_breaker.services.access_control.get_settings") as s:
        s.return_value.unlimited_users = []
        yield TestClient(app)
    app.dependency_overrides.clear()


def _post_audio(client, payload: bytes = b"x" * 100, content_type: str = "audio/webm"):
    return client.post(
        "/api/coach/transcribe",
        files={"audio": ("clip.webm", BytesIO(payload), content_type)},
    )


def test_returns_text_on_success(client):
    with patch(
        "hr_breaker.api.routes.transcribe.transcribe", new=AsyncMock(return_value="hello")
    ):
        r = _post_audio(client)
    assert r.status_code == 200
    assert r.json() == {"text": "hello"}


def test_blob_too_large_returns_413(client):
    payload = b"x" * (5 * 1024 * 1024 + 1)
    with patch("hr_breaker.api.routes.transcribe.transcribe", new=AsyncMock(return_value="x")):
        r = _post_audio(client, payload=payload)
    assert r.status_code == 413
    assert r.json()["detail"] == "Audio too long"


def test_empty_transcript_returns_422(client):
    with patch(
        "hr_breaker.api.routes.transcribe.transcribe",
        new=AsyncMock(side_effect=EmptyTranscriptError("Empty transcript")),
    ):
        r = _post_audio(client)
    assert r.status_code == 422
    assert r.json()["detail"] == "Empty transcript"


def test_provider_failure_returns_502(client):
    with patch(
        "hr_breaker.api.routes.transcribe.transcribe",
        new=AsyncMock(side_effect=ProviderTranscriptionError("Transcription failed")),
    ):
        r = _post_audio(client)
    assert r.status_code == 502
    assert r.json()["detail"] == "Transcription failed"


def test_rate_limit_returns_429(client):
    with patch(
        "hr_breaker.api.routes.transcribe.transcribe", new=AsyncMock(return_value="ok")
    ):
        assert _post_audio(client).status_code == 200
        assert _post_audio(client).status_code == 200
        r = _post_audio(client)
    assert r.status_code == 429
    assert r.json()["detail"] == "Rate limit exceeded"


def test_requires_coach_feature(fake_supabase):
    # Free tier — no coach access (COACH requires offer_mode per FEATURE_MIN_TIER).
    fake_supabase.get_profile.return_value = {
        **_offer_mode_profile(),
        "subscription_tier": "free",
        "subscription_status": "active",
    }
    app.dependency_overrides[get_supabase_service] = lambda: fake_supabase
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_current_user_email] = lambda: (USER, EMAIL)
    with patch("hr_breaker.services.access_control.get_settings") as s:
        s.return_value.unlimited_users = []
        c = TestClient(app)
        with patch(
            "hr_breaker.api.routes.transcribe.transcribe", new=AsyncMock(return_value="x")
        ):
            r = _post_audio(c)
    app.dependency_overrides.clear()
    assert r.status_code == 402
