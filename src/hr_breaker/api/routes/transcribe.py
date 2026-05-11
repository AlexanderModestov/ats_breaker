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
