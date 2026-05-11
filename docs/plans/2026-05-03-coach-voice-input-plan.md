# Coach Voice Input Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` (parallel session) or `superpowers:subagent-driven-development` (this session) to implement this plan task-by-task.

**Goal:** Mobile users hold a mic button in the Coach chat, speak, release, and their words appear as a sent message — transcribed server-side via Gemini.

**Architecture:** Browser captures `audio/webm;codecs=opus` (or `audio/mp4` on iOS) via `MediaRecorder`, uploads as multipart to `POST /api/coach/transcribe`. Backend wraps Gemini Flash through pydantic-ai's `BinaryContent` (consistent with rest of repo, which never calls `google.generativeai` directly). Transcript is returned as JSON, frontend stuffs it into the textarea and immediately calls `handleSend()`.

**Tech Stack:** FastAPI · pydantic-ai (Gemini Flash) · Next.js 16 (React 19) · TanStack Query (already wired) · PostHog (already wired) · No new third-party deps.

**Design source:** `docs/plans/2026-05-03-coach-voice-input-design.md`

---

## Decisions that diverge from the design (read first)

The design was written before exploring the codebase. These changes preserve the design's intent while matching project reality:

| Design said | Plan does | Why |
|---|---|---|
| Hardcode `gemini-2.0-flash` | Use `settings.gemini_flash_model` (currently `gemini-3-flash-preview`) | Recent commit `5dfb5b8 rollback to the pro model everywhere` — hardcoded models contradict project convention. |
| Raw `google.generativeai` SDK | `pydantic_ai.Agent` + `BinaryContent` | Project has zero direct `genai` calls; all LLM goes through pydantic-ai. |
| "Toast" components | Inline `<Alert variant="destructive">` under the input, auto-clears | No toast library is installed. Project surfaces errors with `<Alert>`. |
| `slowapi` for rate limit | Tiny in-memory limiter (~15 lines) keyed by user_id | Avoids new dep; single-process FastAPI is fine per design's own note. |
| Test path `tests/api/` | `tests/test_transcribe_routes.py` | Repo flat-tests pattern. |

Everything else matches the design.

---

## Task list

Dependency order — each task commits independently:

| # | Task | Touches | Depends on |
|---|---|---|---|
| 1 | Transcriber service (Gemini wrapper) | `src/hr_breaker/services/transcriber.py` | — |
| 2 | In-memory rate limiter | `src/hr_breaker/services/voice_rate_limit.py` | — |
| 3 | `POST /api/coach/transcribe` route | `src/hr_breaker/api/routes/transcribe.py`, schemas | 1, 2 |
| 4 | Wire router into the app | `src/hr_breaker/api/routes/__init__.py`, `src/hr_breaker/api/main.py` | 3 |
| 5 | Mobile / MediaRecorder feature-detect helpers | `frontend/src/lib/utils.ts` | — |
| 6 | `transcribeAudio()` client | `frontend/src/lib/api.ts`, `frontend/src/types/index.ts` | 4 |
| 7 | `useVoiceRecorder` hook | `frontend/src/hooks/useVoiceRecorder.ts` | 5 |
| 8 | `<VoiceButton>` component | `frontend/src/components/VoiceButton.tsx` | 7 |
| 9 | Integrate into `<CoachChat>` (conditional render, inline error, auto-send) | `frontend/src/components/CoachChat.tsx` | 6, 8 |
| 10 | PostHog analytics events | `frontend/src/hooks/useAnalytics.ts`, callsites in 7/8/9 | 9 |
| 11 | Final smoke test + type/lint/tests pass | — | 1–10 |

---

## Task 1 — Transcriber service

**Files:**
- Create: `src/hr_breaker/services/transcriber.py`
- Create: `tests/test_transcriber.py`

**Step 1 — Write failing tests**

`tests/test_transcriber.py`:

```python
"""Tests for the voice transcriber service."""

from unittest.mock import AsyncMock, patch

import pytest

from hr_breaker.services.transcriber import TranscriptionError, transcribe


@pytest.mark.asyncio
async def test_transcribe_returns_stripped_text():
    fake_agent = AsyncMock()
    fake_agent.run.return_value.output = "  hello world  \n"
    with patch(
        "hr_breaker.services.transcriber._get_agent", return_value=fake_agent
    ):
        result = await transcribe(b"audio-bytes", "audio/webm;codecs=opus")
    assert result == "hello world"
    fake_agent.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_transcribe_raises_on_empty_output():
    fake_agent = AsyncMock()
    fake_agent.run.return_value.output = "   "
    with patch(
        "hr_breaker.services.transcriber._get_agent", return_value=fake_agent
    ):
        with pytest.raises(TranscriptionError, match="Empty transcript"):
            await transcribe(b"audio-bytes", "audio/webm;codecs=opus")


@pytest.mark.asyncio
async def test_transcribe_wraps_provider_errors():
    fake_agent = AsyncMock()
    fake_agent.run.side_effect = RuntimeError("gemini 503")
    with patch(
        "hr_breaker.services.transcriber._get_agent", return_value=fake_agent
    ):
        with pytest.raises(TranscriptionError, match="Transcription failed"):
            await transcribe(b"audio-bytes", "audio/webm;codecs=opus")
```

**Step 2 — Run, expect FAIL (module not found)**

```bash
uv run pytest tests/test_transcriber.py -v
```
Expected: `ModuleNotFoundError: hr_breaker.services.transcriber`

**Step 3 — Implement**

`src/hr_breaker/services/transcriber.py`:

```python
"""Audio transcription via Gemini (through pydantic-ai)."""

from __future__ import annotations

import logging

from pydantic_ai import Agent, BinaryContent

from hr_breaker.config import get_model_settings, get_settings

logger = logging.getLogger(__name__)


_PROMPT = (
    "Transcribe this audio verbatim. Detect the language automatically. "
    "Return only the transcript text, no commentary, no language label, "
    "no quotes around the text."
)


class TranscriptionError(Exception):
    """Raised when Gemini returns an empty transcript or the provider call fails."""


def _get_agent() -> Agent:
    settings = get_settings()
    return Agent(
        f"google-gla:{settings.gemini_flash_model}",
        model_settings=get_model_settings(),
    )


async def transcribe(audio_bytes: bytes, mime_type: str) -> str:
    """Transcribe audio bytes to text using Gemini Flash.

    Raises TranscriptionError on empty transcript or provider failure.
    """
    agent = _get_agent()
    try:
        result = await agent.run([_PROMPT, BinaryContent(data=audio_bytes, media_type=mime_type)])
    except Exception as exc:
        logger.warning("transcribe: provider error: %s", exc)
        raise TranscriptionError("Transcription failed") from exc

    text = (result.output or "").strip()
    if not text:
        raise TranscriptionError("Empty transcript")
    return text
```

**Step 4 — Run, expect PASS**

```bash
uv run pytest tests/test_transcriber.py -v
```
Expected: `3 passed`.

**Step 5 — Commit**

```bash
git add src/hr_breaker/services/transcriber.py tests/test_transcriber.py
git commit -m "feat(coach): add Gemini-backed audio transcriber service"
```

---

## Task 2 — In-memory rate limiter

**Files:**
- Create: `src/hr_breaker/services/voice_rate_limit.py`
- Create: `tests/test_voice_rate_limit.py`

Per-user limit: 60 requests per rolling hour. Single-process only — fine for current scale.

**Step 1 — Write failing tests**

`tests/test_voice_rate_limit.py`:

```python
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
```

**Step 2 — Run, expect FAIL**

```bash
uv run pytest tests/test_voice_rate_limit.py -v
```
Expected: `ModuleNotFoundError`.

**Step 3 — Implement**

`src/hr_breaker/services/voice_rate_limit.py`:

```python
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
```

**Step 4 — Run, expect PASS**

```bash
uv run pytest tests/test_voice_rate_limit.py -v
```
Expected: `4 passed`.

**Step 5 — Commit**

```bash
git add src/hr_breaker/services/voice_rate_limit.py tests/test_voice_rate_limit.py
git commit -m "feat(coach): add in-memory voice rate limiter (60/hr/user)"
```

---

## Task 3 — `POST /api/coach/transcribe` route

**Files:**
- Create: `src/hr_breaker/api/routes/transcribe.py`
- Create: `tests/test_transcribe_routes.py`
- Modify: `src/hr_breaker/api/schemas.py` (add `TranscribeResponse`)

**Step 1 — Add response schema**

Append to `src/hr_breaker/api/schemas.py`:

```python
class TranscribeResponse(BaseModel):
    """Result of /api/coach/transcribe."""

    text: str
```

**Step 2 — Write failing tests**

`tests/test_transcribe_routes.py`:

```python
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
```

**Step 3 — Run, expect FAIL**

```bash
uv run pytest tests/test_transcribe_routes.py -v
```
Expected: imports fail (`transcribe.py` and `get_voice_rate_limiter` missing).

**Step 4 — Implement the route**

`src/hr_breaker/api/routes/transcribe.py`:

```python
"""Audio transcription endpoint for the Coach voice input."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from hr_breaker.api.deps import CurrentUser, require_feature
from hr_breaker.api.schemas import TranscribeResponse
from hr_breaker.services.tiers import Feature
from hr_breaker.services.transcriber import (
    EmptyTranscriptError,
    ProviderTranscriptionError,
    transcribe,
)
from hr_breaker.services.voice_rate_limit import (
    VoiceRateLimiter,
    get_voice_rate_limiter,
)

logger = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 5 * 1024 * 1024  # 5 MB

router = APIRouter(dependencies=[Depends(require_feature(Feature.COACH))])


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    user_id: CurrentUser,
    limiter: Annotated[VoiceRateLimiter, Depends(get_voice_rate_limiter)],
    audio: UploadFile = File(...),
) -> TranscribeResponse:
    if not limiter.allow(user_id):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    audio_bytes = await audio.read()
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio too long")

    mime_type = audio.content_type or "audio/webm"
    try:
        text = await transcribe(audio_bytes, mime_type)
    except EmptyTranscriptError as exc:
        raise HTTPException(status_code=422, detail="Empty transcript") from exc
    except ProviderTranscriptionError as exc:
        raise HTTPException(status_code=502, detail="Transcription failed") from exc

    return TranscribeResponse(text=text)
```

**Step 5 — Run, expect PASS**

```bash
uv run pytest tests/test_transcribe_routes.py -v
```
Expected: `6 passed`.

**Step 6 — Wire the router into the app**

The route tests in Step 2 hit `app` from `hr_breaker.api.main`, so they require the router to be mounted — otherwise every test returns 404. Do this before running Step 7.

In `src/hr_breaker/api/routes/__init__.py`, alongside the existing imports add:

```python
from .transcribe import router as transcribe_router
```

And add `"transcribe_router"` to `__all__`.

In `src/hr_breaker/api/main.py`:

- Import `transcribe_router` from the same routes module.
- Mount under the existing coach prefix, directly under the existing `coach_router` registration (line 45):

```python
app.include_router(transcribe_router, prefix="/api/coach", tags=["coach"])
```

**Step 7 — Run, expect PASS**

```bash
uv run pytest tests/test_transcribe_routes.py tests/test_coach_routes.py -v
```
Expected: `6 passed` for the new file, all existing coach tests still green.

**Step 8 — Commit**

```bash
git add src/hr_breaker/api/routes/transcribe.py src/hr_breaker/api/schemas.py tests/test_transcribe_routes.py src/hr_breaker/api/routes/__init__.py src/hr_breaker/api/main.py
git commit -m "feat(coach): POST /api/coach/transcribe with size cap and rate limit"
```

---

## Task 4 — _(merged into Task 3)_

Originally a separate "wire the router into the app" task, but the Task 3 tests hit the mounted route through `hr_breaker.api.main.app`, so the wiring had to be in the same commit to make the TDD step land cleanly. See Task 3 Step 6.

---

## Task 5 — Frontend feature-detect helpers

**Files:**
- Modify: `frontend/src/lib/utils.ts`

The codebase has no frontend test runner, so this task is implementation-only with manual verification via `tsc --noEmit`.

**Step 1 — Add helpers**

Append to `frontend/src/lib/utils.ts`:

```ts
/**
 * Coarse pointer + narrow viewport — best proxy we have for "phone/tablet
 * in portrait". SSR-safe (returns false when window is missing).
 */
export function isMobileDevice(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(pointer: coarse)").matches && window.innerWidth < 768;
}

/**
 * Whether the browser can record audio in a MIME type Gemini accepts.
 * We try opus first; fall back to mp4 (iOS Safari).
 */
export function pickRecorderMimeType(): string | null {
  if (typeof MediaRecorder === "undefined") return null;
  if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) return "audio/webm;codecs=opus";
  if (MediaRecorder.isTypeSupported("audio/mp4")) return "audio/mp4";
  return null;
}

export function isVoiceRecordingSupported(): boolean {
  return (
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia &&
    pickRecorderMimeType() !== null
  );
}
```

**Step 2 — Type-check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

**Step 3 — Commit**

```bash
git add frontend/src/lib/utils.ts
git commit -m "feat(coach): add mobile + MediaRecorder feature-detect helpers"
```

---

## Task 6 — `transcribeAudio()` client

**Files:**
- Modify: `frontend/src/lib/api.ts`

**Step 1 — Add the function**

In `frontend/src/lib/api.ts`, near the bottom of the Coach API section, add:

```ts
export async function transcribeAudio(blob: Blob): Promise<string> {
  const headers = await getAuthHeaders();
  const form = new FormData();
  // Filename matters only for Content-Disposition; backend reads bytes + content_type.
  form.append("audio", blob, "clip.webm");

  const response = await fetch(`${API_BASE}/coach/transcribe`, {
    method: "POST",
    headers: { Authorization: (headers as Record<string, string>).Authorization },
    body: form,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = typeof body?.detail === "string" ? body.detail : `Request failed: ${response.status}`;
    throw new ApiError(detail, response.status, body?.detail);
  }

  const { text } = (await response.json()) as { text: string };
  return text;
}
```

**Step 2 — Type-check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

**Step 3 — Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(coach): add transcribeAudio() API client"
```

---

## Task 7 — `useVoiceRecorder` hook

**Files:**
- Create: `frontend/src/hooks/useVoiceRecorder.ts`

State machine: `idle | recording | uploading | error`. Exposes `start()`, `stop()`, `cancel()`, plus live `state` and `durationMs`. Caller handles the upload + transcription — this hook only deals with capture.

**Step 1 — Implement**

```ts
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { pickRecorderMimeType } from "@/lib/utils";

export type RecorderState = "idle" | "recording" | "uploading" | "error";

export type RecorderError =
  | "permission_denied"
  | "no_microphone"
  | "unsupported"
  | "too_short"
  | "max_duration"
  | "unknown";

const MIN_DURATION_MS = 500;
const MAX_DURATION_MS = 60_000;

interface UseVoiceRecorderResult {
  state: RecorderState;
  durationMs: number;
  error: RecorderError | null;
  /** Begin capture. Resolves once recording has actually started (or rejects). */
  start: () => Promise<void>;
  /** Stop and resolve with the blob (or null if too short or empty). */
  stop: () => Promise<Blob | null>;
  /** Stop and discard. */
  cancel: () => void;
  /** Mark the hook as uploading / done — purely cosmetic for the UI button. */
  setUploading: (uploading: boolean) => void;
  /** Reset back to idle. */
  reset: () => void;
}

export function useVoiceRecorder(): UseVoiceRecorderResult {
  const [state, setState] = useState<RecorderState>("idle");
  const [durationMs, setDurationMs] = useState(0);
  const [error, setError] = useState<RecorderError | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startedAtRef = useRef<number>(0);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const maxTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancelledRef = useRef(false);
  const stopResolverRef = useRef<((blob: Blob | null) => void) | null>(null);

  const cleanup = useCallback(() => {
    if (tickRef.current) clearInterval(tickRef.current);
    if (maxTimerRef.current) clearTimeout(maxTimerRef.current);
    tickRef.current = null;
    maxTimerRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    recorderRef.current = null;
    chunksRef.current = [];
  }, []);

  useEffect(() => () => cleanup(), [cleanup]);

  const start = useCallback(async () => {
    // Guard against double-start (flaky touch events, StrictMode dev double-invoke).
    if (recorderRef.current || streamRef.current) return;

    setError(null);
    cancelledRef.current = false;
    const mime = pickRecorderMimeType();
    if (!mime) {
      setError("unsupported");
      setState("error");
      return;
    }

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      const name =
        e && typeof e === "object" && "name" in e
          ? (e as { name?: string }).name
          : undefined;
      setError(
        name === "NotAllowedError" || name === "SecurityError"
          ? "permission_denied"
          : name === "NotFoundError" || name === "NotReadableError"
            ? "no_microphone"
            : "unknown",
      );
      setState("error");
      throw e;
    }

    // User may have released the button while the permission dialog was up.
    if (cancelledRef.current) {
      stream.getTracks().forEach((t) => t.stop());
      setState("idle");
      return;
    }

    const recorder = new MediaRecorder(stream, { mimeType: mime, audioBitsPerSecond: 32000 });
    recorderRef.current = recorder;
    streamRef.current = stream;
    chunksRef.current = [];

    recorder.ondataavailable = (ev) => {
      if (ev.data && ev.data.size > 0) chunksRef.current.push(ev.data);
    };

    // onstop is set ONCE at recorder creation so it fires correctly regardless of who
    // triggers `recorder.stop()` (the consumer via stop(), or the max-duration timer).
    recorder.onstop = () => {
      const chunks = chunksRef.current;
      const mimeUsed = recorder.mimeType || "audio/webm";
      const blob = chunks.length ? new Blob(chunks, { type: mimeUsed }) : null;
      const elapsed = performance.now() - startedAtRef.current;
      const resolve = stopResolverRef.current;
      stopResolverRef.current = null;
      const cancelled = cancelledRef.current;
      cleanup();
      if (cancelled) {
        setState("idle");
        resolve?.(null);
        return;
      }
      if (elapsed < MIN_DURATION_MS) {
        setError("too_short");
        setState("error");
        resolve?.(null);
        return;
      }
      setState("idle");
      resolve?.(blob);
    };

    startedAtRef.current = performance.now();
    setDurationMs(0);
    tickRef.current = setInterval(() => {
      setDurationMs(Math.round(performance.now() - startedAtRef.current));
    }, 100);

    maxTimerRef.current = setTimeout(() => {
      if (recorderRef.current?.state === "recording") {
        // v1: treat overflow as cancellation (recording is discarded). The consumer
        // surfaces a "Max 60 seconds reached" message via the error state. A future
        // version could stash the partial blob and deliver it on release.
        cancelledRef.current = true;
        setError("max_duration");
        recorderRef.current.stop();
      }
    }, MAX_DURATION_MS);

    recorder.start();
    setState("recording");
  }, [cleanup]);

  const stop = useCallback(async (): Promise<Blob | null> => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state !== "recording") {
      // Already inactive (max-duration timer fired, or start() never completed).
      return null;
    }
    return new Promise<Blob | null>((resolve) => {
      stopResolverRef.current = resolve;
      recorder.stop();
    });
  }, []);

  const cancel = useCallback(() => {
    cancelledRef.current = true;
    const recorder = recorderRef.current;
    if (recorder && recorder.state === "recording") recorder.stop();
    else {
      cleanup();
      setState("idle");
    }
  }, [cleanup]);

  const setUploading = useCallback((uploading: boolean) => {
    setState(uploading ? "uploading" : "idle");
  }, []);

  const reset = useCallback(() => {
    setError(null);
    setState("idle");
    setDurationMs(0);
  }, []);

  return { state, durationMs, error, start, stop, cancel, setUploading, reset };
}
```

**Step 2 — Type-check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

**Step 3 — Commit**

```bash
git add frontend/src/hooks/useVoiceRecorder.ts
git commit -m "feat(coach): add useVoiceRecorder hook (MediaRecorder + state machine)"
```

---

## Task 8 — `<VoiceButton>` component

**Files:**
- Create: `frontend/src/components/VoiceButton.tsx`

Pressable circular button. Touch handlers track horizontal swipe; when `currentX - startX < -80`, the next `touchend` becomes a cancel.

**Step 1 — Implement**

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { Mic, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useVoiceRecorder, type RecorderError } from "@/hooks/useVoiceRecorder";

const SWIPE_CANCEL_PX = -80;

interface VoiceButtonProps {
  disabled?: boolean;
  /** Called with the captured audio blob. Caller transcribes + sends. */
  onCaptured: (blob: Blob) => Promise<void>;
  /** Called on user-visible errors so the parent can surface a message. */
  onError: (kind: RecorderError) => void;
  /** Optional telemetry hooks. */
  onRecordingStart?: () => void;
  onRecordingEnd?: (info: { durationMs: number; cancelled: boolean }) => void;
}

function formatDuration(ms: number): string {
  const total = Math.floor(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function VoiceButton({
  disabled,
  onCaptured,
  onError,
  onRecordingStart,
  onRecordingEnd,
}: VoiceButtonProps) {
  const recorder = useVoiceRecorder();
  const [willCancel, setWillCancel] = useState(false);
  const startXRef = useRef<number | null>(null);

  // Surface hook errors upward.
  useEffect(() => {
    if (recorder.error) {
      onError(recorder.error);
      onRecordingEnd?.({ durationMs: recorder.durationMs, cancelled: true });
      recorder.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recorder.error]);

  const handleStart = async (clientX: number) => {
    if (disabled || recorder.state !== "idle") return;
    startXRef.current = clientX;
    setWillCancel(false);
    try {
      await recorder.start();
      onRecordingStart?.();
    } catch {
      // Error already set inside the hook; effect above will surface it.
    }
  };

  const handleMove = (clientX: number) => {
    if (recorder.state !== "recording" || startXRef.current === null) return;
    setWillCancel(clientX - startXRef.current < SWIPE_CANCEL_PX);
  };

  const handleEnd = async () => {
    if (recorder.state !== "recording") return;
    if (willCancel) {
      const dur = recorder.durationMs;
      recorder.cancel();
      onRecordingEnd?.({ durationMs: dur, cancelled: true });
      return;
    }
    const dur = recorder.durationMs;
    const blob = await recorder.stop();
    onRecordingEnd?.({ durationMs: dur, cancelled: false });
    if (!blob) return;
    recorder.setUploading(true);
    try {
      await onCaptured(blob);
    } finally {
      recorder.setUploading(false);
    }
  };

  const isRecording = recorder.state === "recording";
  const isUploading = recorder.state === "uploading";

  return (
    <div className="relative">
      <button
        type="button"
        disabled={disabled || isUploading}
        aria-label={isRecording ? "Release to send, slide left to cancel" : "Hold to record voice message"}
        className={cn(
          "inline-flex h-10 w-10 items-center justify-center rounded-full transition-colors",
          "select-none touch-none",
          isRecording
            ? willCancel
              ? "bg-destructive text-destructive-foreground"
              : "bg-destructive/80 text-destructive-foreground animate-pulse"
            : "bg-primary text-primary-foreground hover:bg-primary/90",
          disabled && "opacity-50 cursor-not-allowed",
        )}
        onTouchStart={(e) => handleStart(e.touches[0].clientX)}
        onTouchMove={(e) => handleMove(e.touches[0].clientX)}
        onTouchEnd={handleEnd}
        onTouchCancel={() => {
          if (recorder.state === "recording") {
            const dur = recorder.durationMs;
            recorder.cancel();
            onRecordingEnd?.({ durationMs: dur, cancelled: true });
          }
        }}
        onMouseDown={(e) => handleStart(e.clientX)}
        onMouseMove={(e) => handleMove(e.clientX)}
        onMouseUp={handleEnd}
        onMouseLeave={() => {
          if (recorder.state === "recording") {
            const dur = recorder.durationMs;
            recorder.cancel();
            onRecordingEnd?.({ durationMs: dur, cancelled: true });
          }
        }}
      >
        {isUploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mic className="h-4 w-4" />}
      </button>

      {isRecording && (
        <div
          className={cn(
            "absolute -top-9 right-0 whitespace-nowrap rounded-md border border-border bg-background px-2 py-1 text-xs shadow-sm",
            willCancel ? "text-destructive" : "text-muted-foreground",
          )}
        >
          {formatDuration(recorder.durationMs)} ·{" "}
          {willCancel ? "← Release to cancel" : "← slide to cancel"}
        </div>
      )}
    </div>
  );
}
```

**Step 2 — Type-check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

**Step 3 — Commit**

```bash
git add frontend/src/components/VoiceButton.tsx
git commit -m "feat(coach): add VoiceButton with push-to-hold and slide-to-cancel"
```

---

## Task 9 — Integrate into `<CoachChat>`

**Files:**
- Modify: `frontend/src/components/CoachChat.tsx`

**Step 1 — Add imports & state**

At the top of `CoachChat.tsx`:

```ts
import { isMobileDevice, isVoiceRecordingSupported } from "@/lib/utils";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { VoiceButton } from "@/components/VoiceButton";
import { transcribeAudio } from "@/lib/api";
import { ApiError } from "@/lib/api"; // ApiError is exported from api.ts already
```

Inside the `CoachChat` component body (after the existing hooks):

```ts
const [voiceSupported, setVoiceSupported] = useState(false);
useEffect(() => {
  setVoiceSupported(isMobileDevice() && isVoiceRecordingSupported());
}, []);

const [voiceError, setVoiceError] = useState<string | null>(null);

const VOICE_ERROR_COPY: Record<string, string> = {
  permission_denied: "Microphone access denied. Enable it in your browser settings.",
  no_microphone: "Microphone unavailable.",
  unsupported: "Voice recording isn't supported in this browser.",
  too_short: "Hold to record.",
  max_duration: "Max 60 seconds reached.",
  unknown: "Couldn't start recording.",
};

const handleVoiceCaptured = useCallback(
  async (blob: Blob) => {
    setVoiceError(null);
    try {
      const text = await transcribeAudio(blob);
      if (!text.trim()) {
        setVoiceError("Didn't catch that.");
        return;
      }
      onSend(text.trim());
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.status === 413) setVoiceError("Recording too long.");
        else if (e.status === 422) setVoiceError("Didn't catch that.");
        else if (e.status === 429) setVoiceError("Too many voice messages. Wait a bit.");
        else setVoiceError("Couldn't transcribe. Try again.");
      } else {
        setVoiceError("Couldn't transcribe. Try again.");
      }
    }
  },
  [onSend],
);
```

**Step 2 — Conditional render**

Replace the existing `<Button size="icon" onClick={handleSend} ...>` block with:

```tsx
{voiceSupported && !input.trim() ? (
  <VoiceButton
    disabled={isStreaming}
    onCaptured={handleVoiceCaptured}
    onError={(kind) => setVoiceError(VOICE_ERROR_COPY[kind] ?? VOICE_ERROR_COPY.unknown)}
  />
) : (
  <Button size="icon" onClick={handleSend} disabled={!input.trim() || isStreaming}>
    {isStreaming ? (
      <Loader2 className="h-4 w-4 animate-spin" />
    ) : (
      <Send className="h-4 w-4" />
    )}
  </Button>
)}
```

**Step 3 — Inline error surface**

Directly below the `<div className="flex items-end gap-2">…</div>` row (still inside the bottom border-t container), add:

```tsx
{voiceError && (
  <Alert variant="destructive" className="mt-2 py-2 text-xs">
    <AlertDescription>{voiceError}</AlertDescription>
  </Alert>
)}
```

The error clears on the next successful send (we already clear it at the top of `handleVoiceCaptured`) and on every keystroke (add a one-liner inside `handleResize`: `if (voiceError) setVoiceError(null);`).

**Step 4 — Type-check + lint**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```
Expected: no errors.

**Step 5 — Commit**

```bash
git add frontend/src/components/CoachChat.tsx
git commit -m "feat(coach): wire VoiceButton into CoachChat (auto-send on transcribe)"
```

---

## Task 10 — PostHog analytics

**Files:**
- Modify: `frontend/src/hooks/useAnalytics.ts`
- Modify: `frontend/src/components/CoachChat.tsx` (call sites)

**Step 1 — Extend the event union**

In `frontend/src/hooks/useAnalytics.ts`, add to `AnalyticsEvent`:

```ts
| "coach_voice_recording_started"
| "coach_voice_recording_completed"
| "coach_voice_error"
```

**Step 2 — Emit events from CoachChat**

In `CoachChat.tsx`:

```ts
const { track } = useAnalytics();
```

Wire the `VoiceButton` props:

```tsx
<VoiceButton
  disabled={isStreaming}
  onCaptured={handleVoiceCaptured}
  onError={(kind) => {
    track("coach_voice_error", { error_type: kind });
    setVoiceError(VOICE_ERROR_COPY[kind] ?? VOICE_ERROR_COPY.unknown);
  }}
  onRecordingStart={() => track("coach_voice_recording_started")}
  onRecordingEnd={({ durationMs, cancelled }) =>
    track("coach_voice_recording_completed", { duration_ms: durationMs, cancelled })
  }
/>
```

Inside `handleVoiceCaptured`, after the successful transcription, also emit:

```ts
track("coach_voice_recording_completed", { transcript_length: text.trim().length, cancelled: false, duration_ms: 0 });
```

…or — simpler — only emit the completed event from `onRecordingEnd` and skip the second call to avoid double-counting. **Use the simpler form** unless `transcript_length` is needed later.

In the `ApiError` 429 branch, also emit:

```ts
track("coach_voice_error", { error_type: "rate_limited" });
```

…and for the 502/empty/unknown branches:

```ts
track("coach_voice_error", { error_type: "transcription_failed" });
```

**Step 3 — Type-check + lint**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```
Expected: no errors.

**Step 4 — Commit**

```bash
git add frontend/src/hooks/useAnalytics.ts frontend/src/components/CoachChat.tsx
git commit -m "feat(coach): add PostHog events for voice input flow"
```

---

## Task 11 — Final verification

**Step 1 — Full backend test suite**

```bash
uv run pytest -x
```
Expected: all green; no new warnings beyond what `main` already has.

**Step 2 — Frontend type-check + lint + build**

```bash
cd frontend && npx tsc --noEmit && npm run lint && npm run build
```
Expected: clean build.

**Step 3 — Manual smoke test (real mobile device required)**

Follow the design's checklist verbatim (`docs/plans/2026-05-03-coach-voice-input-design.md` § Verification):

1. `/coach` on phone → 🎤 visible right of empty textarea.
2. Type a character → 🎤 → ➤. Delete → back to 🎤.
3. Hold 🎤 → permission prompt → grant.
4. Speak 5–10 s → release → text appears, auto-sends.
5. Hold → speak → slide finger left → release → nothing sent.
6. Hold → release within 200 ms → inline `Hold to record` shown.
7. Hold → speak 65 s → auto-stop at 60 s, message sent.
8. iOS Safari: same flow works using `audio/mp4`.
9. `/coach` on desktop → no 🎤 button, send works as before.

Document any deviation as a follow-up.

**Step 4 — (Optional) Final commit if any small touch-ups**

```bash
git status
```

---

## Files created / modified summary

**Backend (new):**
- `src/hr_breaker/services/transcriber.py`
- `src/hr_breaker/services/voice_rate_limit.py`
- `src/hr_breaker/api/routes/transcribe.py`
- `tests/test_transcriber.py`
- `tests/test_voice_rate_limit.py`
- `tests/test_transcribe_routes.py`

**Backend (modified):**
- `src/hr_breaker/api/schemas.py` (+1 model)
- `src/hr_breaker/api/routes/__init__.py` (+1 export)
- `src/hr_breaker/api/main.py` (+1 `include_router`)

**Frontend (new):**
- `frontend/src/hooks/useVoiceRecorder.ts`
- `frontend/src/components/VoiceButton.tsx`

**Frontend (modified):**
- `frontend/src/lib/utils.ts` (+3 helpers)
- `frontend/src/lib/api.ts` (+1 fn)
- `frontend/src/components/CoachChat.tsx` (conditional render, error UI, analytics)
- `frontend/src/hooks/useAnalytics.ts` (+3 event names)

**No DB migration. No new env vars. No new dependencies.**
