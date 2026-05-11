"""Simple in-memory per-user rate limiter for voice transcription.

Single-process only. Move to a shared store if we go multi-process.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class VoiceRateLimiter:
    def __init__(self, max_per_window: int = 60, window_seconds: int = 3600) -> None:
        self._max = max_per_window
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, user_id: str) -> bool:
        """Return True if this request is within the limit; record it."""
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            q = self._hits[user_id]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self._max:
                return False
            q.append(now)
            return True


_default = VoiceRateLimiter()


def get_voice_rate_limiter() -> VoiceRateLimiter:
    """FastAPI-friendly accessor; tests can override via dependency_overrides."""
    return _default
