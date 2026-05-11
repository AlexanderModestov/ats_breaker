"""Tests for the voice transcriber service."""

from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai import BinaryContent

from hr_breaker.services.transcriber import (
    EmptyTranscriptError,
    ProviderTranscriptionError,
    TranscriptionError,
    _PROMPT,
    transcribe,
)


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
    (call_args,) = fake_agent.run.await_args.args
    assert isinstance(call_args, list)
    assert call_args[0] == _PROMPT
    binary = call_args[1]
    assert binary.data == b"audio-bytes"
    assert binary.media_type == "audio/webm;codecs=opus"


@pytest.mark.asyncio
async def test_transcribe_raises_on_empty_output():
    fake_agent = AsyncMock()
    fake_agent.run.return_value.output = "   "
    with patch(
        "hr_breaker.services.transcriber._get_agent", return_value=fake_agent
    ):
        with pytest.raises(EmptyTranscriptError, match="Empty transcript"):
            await transcribe(b"audio-bytes", "audio/webm;codecs=opus")


@pytest.mark.asyncio
async def test_transcribe_wraps_provider_errors():
    fake_agent = AsyncMock()
    fake_agent.run.side_effect = RuntimeError("gemini 503")
    with patch(
        "hr_breaker.services.transcriber._get_agent", return_value=fake_agent
    ):
        with pytest.raises(ProviderTranscriptionError, match="Transcription failed"):
            await transcribe(b"audio-bytes", "audio/webm;codecs=opus")


@pytest.mark.asyncio
async def test_subclasses_are_caught_as_base():
    fake_agent = AsyncMock()
    fake_agent.run.return_value.output = "   "
    with patch(
        "hr_breaker.services.transcriber._get_agent", return_value=fake_agent
    ):
        with pytest.raises(TranscriptionError):
            await transcribe(b"x", "audio/webm")
