# Coach Voice Input — Design

**Status:** Approved, ready for implementation plan.
**Scope:** v1 — mobile-only, push-to-hold, auto-send, server-side transcription via Gemini.

---

## Problem

Coach is a chat interface where users prepare for interviews. On mobile, typing long messages is friction. Adding voice input lowers that friction without changing what Coach does.

## Goals

- A user on mobile can hold a microphone button, speak, release, and their words appear in Coach as a sent message.
- Auto-detects language (Russian / English / mix).
- Slide-to-cancel during recording prevents accidental sends.
- Zero new infrastructure: reuses existing Gemini API key and JWT auth.

## Non-goals (explicit, for v1)

- Desktop voice input.
- Waveform visualization during recording.
- Persisting audio blobs to Supabase Storage.
- Text-to-speech (Coach replying with voice).
- Per-tier voice quotas (e.g., "10 minutes/month on Basic").
- Language toggle (auto-detect only).
- Mock-interview / pronunciation analysis features.

These were considered and deferred. Voice is a paid feature only because Coach itself is paid — there is no separate gate.

---

## User flow

### Happy path

1. User opens Coach on mobile. The empty textarea has a 🎤 button on the right (replaces the ➤ Send button until they type a character).
2. User presses and holds 🎤. First time: browser shows microphone permission prompt; user accepts.
3. Button turns into a pulsing red circle. Below the textarea, a thin bar shows `0:01` and the hint `← slide to cancel`.
4. User speaks. `MediaRecorder` captures `audio/webm;codecs=opus` at 32 kbps.
5. User releases. Recorder stops, blob (~10–50 KB for 30 s) uploads to backend. Button shows a spinner.
6. Backend returns transcript. The text briefly fills the textarea, then `handleSend()` fires automatically. The user sees their message in the chat.

### Cancel path

- During recording, user moves finger left. When `currentX − startX < −80px`, the hint flips to `← Release to cancel` (red).
- On `touchend` in the cancel zone, recorder stops, blob is discarded, no upload, no toast.

### Edge: too-short tap (< 500 ms)

- Recorder started but stopped almost immediately. Blob discarded. Toast: `Hold to record.` No upload.

---

## Architecture

```
[Browser MediaRecorder]
  → Blob (audio/webm;codecs=opus, ≤ 5 MB)
  → fetch(POST /api/coach/transcribe, FormData)
  → [FastAPI route, JWT + require_feature("coach")]
  → [transcriber.transcribe(audio_bytes, mime)]
  → [Gemini 2.0 Flash, audio inline]
  → text
  → JSON { "text": "..." }
  → [hook callback → setInput → handleSend]
```

### Frontend

| File | Change |
|------|--------|
| `frontend/src/hooks/useVoiceRecorder.ts` | **New.** Wraps `MediaRecorder` + `getUserMedia` + timer. State machine: `idle | recording | uploading | error`. Exposes `start()`, `stop()`, `cancel()`, `state`, `durationMs`. |
| `frontend/src/components/VoiceButton.tsx` | **New.** Pressable circular button with `touchstart`/`touchmove`/`touchend`/`touchcancel` handlers, pulsing animation, swipe detection. Calls back into the hook. |
| `frontend/src/components/CoachChat.tsx` | **Modify.** Conditional render: `<VoiceButton>` when `input.trim() === ""` && `isMobile`, else `<SendButton>`. Hook callback `onTranscribed(text)` calls `setInput(text); handleSend();`. |
| `frontend/src/lib/utils.ts` | **Add** `isMobileDevice()` — `matchMedia("(pointer: coarse)").matches && window.innerWidth < 768`. Memoized at component mount. |

### Backend

| File | Change |
|------|--------|
| `src/hr_breaker/api/routes/transcribe.py` | **New.** `POST /api/coach/transcribe`. Multipart form with `audio` field, max 5 MB enforced via `File(..., max_size=...)`. Dependencies: `get_current_user`, `require_feature("coach")`. |
| `src/hr_breaker/services/transcriber.py` | **New.** Thin wrapper around `google-generativeai`. Single function `transcribe(audio_bytes: bytes, mime_type: str) -> str`. Raises `TranscriptionError` on empty result or API failure. |
| `src/hr_breaker/api/main.py` | **Modify.** Register the new router. |

No DB migration. No new env vars (reuses `GOOGLE_API_KEY`).

---

## API contract

### `POST /api/coach/transcribe`

**Request:**
```http
POST /api/coach/transcribe
Authorization: Bearer <jwt>
Content-Type: multipart/form-data

audio=<binary, audio/webm;codecs=opus or audio/mp4, max 5 MB>
```

**Success (200):**
```json
{ "text": "Расскажи мне о senior PM роли в этой компании" }
```

**Errors** (project's existing `ApiError` shape):

| Status | `detail` | When |
|--------|----------|------|
| 413 | `Audio too long` | Blob > 5 MB |
| 422 | `Empty transcript` | Gemini returned empty string |
| 429 | `Rate limit exceeded` | > 60 transcriptions/hour for this user |
| 502 | `Transcription failed` | Gemini API exception |

### Gemini call

```python
async def transcribe(audio_bytes: bytes, mime_type: str) -> str:
    model = genai.GenerativeModel("gemini-2.0-flash")
    response = await model.generate_content_async([
        {"mime_type": mime_type, "data": audio_bytes},
        "Transcribe this audio verbatim. Detect the language automatically. "
        "Return only the transcript text, no commentary, no language label, "
        "no quotes around the text.",
    ])
    text = response.text.strip()
    if not text:
        raise TranscriptionError("Empty transcript")
    return text
```

### MediaRecorder config

```ts
const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
  ? "audio/webm;codecs=opus"
  : "audio/mp4"; // iOS Safari fallback
const recorder = new MediaRecorder(stream, {
  mimeType: mime,
  audioBitsPerSecond: 32000,
});
```

If neither MIME type is supported (very old browsers), `isMobileDevice()` is still true but `MediaRecorder.isTypeSupported` returns false for both — the 🎤 button is not rendered. Send button shows as normal.

---

## Edge cases

| Case | Detection | Behavior |
|------|-----------|----------|
| Permission denied | `getUserMedia` throws `NotAllowedError` | Toast `Microphone access denied. Enable it in your browser settings.` Button stays visible; next tap re-prompts (browser decides). |
| Mic missing / busy | `NotFoundError` / `NotReadableError` | Toast `Microphone unavailable.` |
| Tap < 500 ms | `touchend - touchstart < 500` | Discard blob. Toast `Hold to record.` No upload. |
| Recording > 60 s | Internal timer | Auto-stop, upload as if released. Toast `Max 60 seconds reached.` |
| Slide-cancel | `currentX - startX < -80px` on `touchend` | Stop recorder, discard blob, no upload, no toast. |
| Network/Gemini fail | 502 from backend | Toast `Couldn't transcribe. Try again.` State → idle. No retry. |
| Empty transcript | 422 from backend | Toast `Didn't catch that.` |
| Rate limit | 429 from backend | Toast `Too many voice messages. Wait a bit.` |
| Unsupported MediaRecorder | Feature detect at mount | 🎤 button never rendered. |

### Rate limiting

60 requests / hour / user. Implementation: `slowapi` keyed by `user_id` from JWT, in-memory store. Single-process FastAPI is fine for current scale; if multi-process, switch to a Postgres-backed counter later.

---

## Analytics (PostHog)

Three events, enough to validate "do users use this":

- `coach_voice_recording_started` — no props.
- `coach_voice_recording_completed` — `{ duration_ms, cancelled: bool, transcript_length?: number }`.
- `coach_voice_error` — `{ error_type: "permission_denied" | "no_microphone" | "transcription_failed" | "rate_limited" | "too_short" | "max_duration" }`.

**Decision criteria after 2–3 weeks:**
- If voice ≥ 15% of Coach messages → consider desktop rollout.
- If error rate > 10% → investigate before growing scope.
- If usage < 3% → do nothing more (deprioritize).

---

## Verification

### Manual smoke test (real mobile device required)

1. `/coach` on phone → 🎤 visible right of empty textarea.
2. Type a character → 🎤 → ➤. Delete → back to 🎤.
3. Hold 🎤 → permission prompt → grant.
4. Speak 5–10 s → release → text appears in textarea then auto-sends to chat.
5. Hold → speak → slide finger left → release → nothing sent.
6. Hold → release within 200 ms → toast `Hold to record`.
7. Hold → speak 65 s → auto-stop at 60 s, message sent.
8. iOS Safari: same flow works using `audio/mp4`.
9. `/coach` on desktop → no 🎤 button, send works as before.

### Automated

```bash
cd frontend && npx tsc --noEmit
uv run pytest tests/api/
```

No new unit tests required for v1; the surface is small and the value is in the manual flow.

---

## Open questions deferred to implementation

- Exact toast component to reuse (existing project has one — implementer picks).
- Whether to show transcribed text in textarea for ~100 ms before clearing it (subtle confirmation), or pass it directly to `handleSend()` without touching `setInput`. Both are fine; default to the visible-then-send variant unless it causes flicker.
