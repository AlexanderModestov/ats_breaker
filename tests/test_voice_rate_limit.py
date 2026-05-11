"""Tests for the in-memory voice transcription rate limiter."""

import time

from hr_breaker.services.voice_rate_limit import VoiceRateLimiter


def test_under_limit_returns_true():
    limiter = VoiceRateLimiter(max_per_window=3, window_seconds=60)
    assert limiter.allow("u1") is True
    assert limiter.allow("u1") is True
    assert limiter.allow("u1") is True


def test_over_limit_returns_false():
    limiter = VoiceRateLimiter(max_per_window=2, window_seconds=60)
    assert limiter.allow("u1") is True
    assert limiter.allow("u1") is True
    assert limiter.allow("u1") is False


def test_limits_are_per_user():
    limiter = VoiceRateLimiter(max_per_window=1, window_seconds=60)
    assert limiter.allow("u1") is True
    assert limiter.allow("u2") is True
    assert limiter.allow("u1") is False
    assert limiter.allow("u2") is False


def test_old_entries_are_pruned(monkeypatch):
    limiter = VoiceRateLimiter(max_per_window=1, window_seconds=10)
    t = [1_000_000.0]
    monkeypatch.setattr(time, "monotonic", lambda: t[0])
    assert limiter.allow("u1") is True
    assert limiter.allow("u1") is False
    t[0] += 11  # advance past the window
    assert limiter.allow("u1") is True
