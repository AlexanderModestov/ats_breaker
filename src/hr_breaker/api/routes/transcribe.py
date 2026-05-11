"""Audio transcription endpoint for the Coach voice input."""

from __future__ import annotations

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

MAX_AUDIO_BYTES = 5 * 1024 * 1024  # 5 MB


def _check_rate_limit(
    user_id: CurrentUser,
    limiter: Annotated[VoiceRateLimiter, Depends(get_voice_rate_limiter)],
) -> None:
    """Router-level rate-limit gate. Runs before the multipart body is parsed."""
    if not limiter.allow(user_id):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")


router = APIRouter(
    dependencies=[
        Depends(require_feature(Feature.COACH)),
        Depends(_check_rate_limit),
    ]
)


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    audio: UploadFile = File(...),
) -> TranscribeResponse:
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
