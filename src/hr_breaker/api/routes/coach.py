"""Coach API routes — chat streaming + storybank CRUD."""

import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic_ai import ModelMessagesTypeAdapter
from pydantic_core import to_jsonable_python

from hr_breaker.agents.coach import CoachDeps, create_coach_agent
from hr_breaker.api.deps import CurrentUser, SupabaseServiceDep
from hr_breaker.api.schemas import (
    CoachChatRequest,
    CoachMessageResponse,
    CoachSessionResponse,
    StorybankEntryRequest,
    StorybankEntryResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _extract_display_messages(raw_messages: list) -> list[dict]:
    """Extract user/assistant text messages from Pydantic-AI message format."""
    display = []
    for msg in raw_messages:
        if isinstance(msg, dict):
            kind = msg.get("kind") or msg.get("type", "")
            if "request" in kind.lower():
                for part in msg.get("parts", []):
                    part_type = part.get("kind") or part.get("type", "")
                    if "user" in part_type.lower() and "prompt" in part_type.lower():
                        display.append({"role": "user", "content": part.get("content", "")})
            elif "response" in kind.lower():
                for part in msg.get("parts", []):
                    part_type = part.get("kind") or part.get("type", "")
                    if "text" in part_type.lower():
                        display.append({"role": "assistant", "content": part.get("content", "")})
    return display


@router.get("/sessions", response_model=list[CoachSessionResponse])
async def list_sessions(user_id: CurrentUser, supabase: SupabaseServiceDep):
    """List all coach sessions for the current user."""
    return supabase.list_coach_sessions(user_id)


@router.get("/sessions/{session_id}/messages", response_model=list[CoachMessageResponse])
async def get_session_messages(
    session_id: str, user_id: CurrentUser, supabase: SupabaseServiceDep
):
    """Get display messages for a coach session."""
    raw = supabase.get_coach_messages(session_id)
    return _extract_display_messages(raw)


@router.post("/chat")
async def chat(
    body: CoachChatRequest,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
):
    """Stream a coach response via SSE."""
    # Get or create session
    session = supabase.get_or_create_coach_session(user_id, body.optimization_run_id)
    session_id = session["id"]

    # Load optimization run for context
    run = supabase.get_optimization_run(body.optimization_run_id, user_id)
    if not run:
        raise HTTPException(status_code=404, detail="Optimization run not found")

    job_parsed = run.get("job_parsed") or {}

    # Load CV text
    cv_text = ""
    if run.get("cv_id"):
        cv = supabase.get_cv(run["cv_id"], user_id)
        if cv:
            cv_text = cv.get("content_text", "") or ""

    # Load storybank
    storybank = supabase.list_storybank(user_id)

    # Load message history
    raw_history = supabase.get_coach_messages(session_id)
    if raw_history:
        message_history = ModelMessagesTypeAdapter.validate_python(raw_history)
    else:
        message_history = None

    # Create save callback
    async def on_save_story(data: dict):
        return supabase.create_storybank_entry(user_id, data)

    deps = CoachDeps(
        user_id=user_id,
        resume_text=cv_text,
        job_title=job_parsed.get("title", "Unknown"),
        job_company=job_parsed.get("company", "Unknown"),
        job_requirements=job_parsed.get("requirements", []),
        job_keywords=job_parsed.get("keywords", []),
        storybank=storybank,
        on_save_story=on_save_story,
    )

    agent = create_coach_agent()

    async def event_stream() -> AsyncIterator[str]:
        """Generate SSE events from agent stream."""
        try:
            async with agent.run_stream(
                body.message,
                deps=deps,
                message_history=message_history,
            ) as result:
                async for text in result.stream_text(delta=True):
                    data = json.dumps({"type": "delta", "content": text})
                    yield f"data: {data}\n\n"

                # Stream done — save full history
                all_messages = result.all_messages()
                serialized = to_jsonable_python(all_messages)
                supabase.save_coach_messages(session_id, serialized)

                # Send done event with session_id
                done = json.dumps({"type": "done", "session_id": session_id})
                yield f"data: {done}\n\n"

        except Exception as e:
            logger.error(f"Coach stream error: {e}")
            error = json.dumps({"type": "error", "content": str(e)})
            yield f"data: {error}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# Storybank CRUD
@router.get("/storybank", response_model=list[StorybankEntryResponse])
async def list_storybank(user_id: CurrentUser, supabase: SupabaseServiceDep):
    """List all storybank entries."""
    return supabase.list_storybank(user_id)


@router.post("/storybank", response_model=StorybankEntryResponse, status_code=201)
async def create_storybank_entry(
    body: StorybankEntryRequest,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
):
    """Create a new storybank entry."""
    return supabase.create_storybank_entry(user_id, body.model_dump())


@router.put("/storybank/{entry_id}", response_model=StorybankEntryResponse)
async def update_storybank_entry(
    entry_id: str,
    body: StorybankEntryRequest,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
):
    """Update a storybank entry."""
    result = supabase.update_storybank_entry(entry_id, user_id, body.model_dump())
    if not result:
        raise HTTPException(status_code=404, detail="Storybank entry not found")
    return result


@router.delete("/storybank/{entry_id}", status_code=204)
async def delete_storybank_entry(
    entry_id: str,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
):
    """Delete a storybank entry."""
    if not supabase.delete_storybank_entry(entry_id, user_id):
        raise HTTPException(status_code=404, detail="Storybank entry not found")
