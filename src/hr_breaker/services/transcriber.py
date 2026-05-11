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
