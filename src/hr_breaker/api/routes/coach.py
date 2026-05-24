"""Coach API routes — chat streaming."""

import asyncio
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
    CoachThreadCreateRequest,
    CoachThreadUpdateRequest,
)
from hr_breaker.services.tiers import coach_is_unlimited

logger = logging.getLogger(__name__)

router = APIRouter()


def _extract_display_messages(raw_messages: list) -> list[dict]:
    """Extract user/assistant text messages from Pydantic-AI message format.

    Consecutive assistant TextParts (across ModelResponses split by tool calls)
    are merged into one message so the reloaded history matches the streamed
    bubble, which concatenates all deltas into a single assistant message.
    """
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        TextPart,
        UserPromptPart,
    )

    display = []
    try:
        messages = ModelMessagesTypeAdapter.validate_python(raw_messages)
    except Exception:
        return display

    for msg in messages:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, UserPromptPart):
                    display.append({"role": "user", "content": part.content})
        elif isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, TextPart):
                    if display and display[-1]["role"] == "assistant":
                        display[-1]["content"] += part.content
                    else:
                        display.append({"role": "assistant", "content": part.content})
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
    # Verify session belongs to user
    sessions = supabase.list_coach_sessions(user_id)
    if not any(s["id"] == session_id for s in sessions):
        raise HTTPException(status_code=404, detail="Session not found")
    raw = supabase.get_coach_messages(session_id)
    return _extract_display_messages(raw)


_COMPANY_CAP_ERROR = {
    "code": "coach_company_limit",
    "message": "Free plan is limited to one company. Upgrade to Offer Mode to practice with multiple companies.",
}


def _check_company_cap(profile: dict, run: dict, supabase, user_id: str) -> None:
    """Raise 403 if a trial user tries to create a session for a different company identity."""
    if coach_is_unlimited(profile):
        return
    locked_company, locked_run_id = supabase.get_coach_lock(user_id)
    if locked_company is None and locked_run_id is None:
        return  # No sessions yet — allow anything.
    new_company = ((run.get("job_parsed") or {}).get("company") or "").strip()
    new_company_known = bool(new_company) and new_company.lower() != "unknown"
    if locked_company is not None:
        # Locked to a known company — new session must have the same company.
        if not new_company_known or new_company.lower() != locked_company.lower():
            raise HTTPException(
                status_code=403,
                detail={**_COMPANY_CAP_ERROR, "locked_company": locked_company},
            )
    else:
        # Locked to a specific run (unknown company) — new session must be for that same run.
        if run.get("id") != locked_run_id:
            raise HTTPException(
                status_code=403,
                detail={**_COMPANY_CAP_ERROR, "locked_company": None},
            )


@router.post("/sessions", response_model=CoachSessionResponse, status_code=201)
async def create_thread(
    body: CoachThreadCreateRequest,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
):
    """Create an empty coach thread for a position."""
    profile = supabase.get_profile(user_id) or {}
    run = supabase.get_optimization_run(body.optimization_run_id, user_id)
    if not run:
        raise HTTPException(status_code=404, detail="Optimization run not found")
    _check_company_cap(profile, run, supabase, user_id)
    session = supabase.create_coach_session(user_id, body.optimization_run_id)
    return {**session, "preview": None, "message_count": 0}


@router.patch("/sessions/{session_id}", response_model=CoachSessionResponse)
async def rename_thread(
    session_id: str,
    body: CoachThreadUpdateRequest,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
):
    """Update thread title. Returns the updated session shape with stale
    preview/count fields — caller should invalidate the sessions list to
    refresh those values."""
    updated = supabase.update_coach_session_title(session_id, user_id, body.title)
    if not updated:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {**updated, "preview": None, "message_count": 0}


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_thread(
    session_id: str,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
):
    """Delete a coach thread (cascades to messages)."""
    if not supabase.delete_coach_session(session_id, user_id):
        raise HTTPException(status_code=404, detail="Thread not found")


@router.post("/chat")
async def chat(
    body: CoachChatRequest,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
):
    """Stream a coach response via SSE.

    Accepts either body.thread_id (existing thread) or body.optimization_run_id
    (lazy-create new thread). Schema validator enforces exactly-one-of.
    """
    # Resolve thread.
    if body.thread_id:
        session = supabase.get_coach_session(body.thread_id, user_id)
        if not session:
            raise HTTPException(status_code=404, detail="Thread not found")
        optimization_run_id = session["optimization_run_id"]
    else:
        # Lazy create: enforce company cap, then ensure run is owned by the user.
        profile = supabase.get_profile(user_id) or {}
        check_run = supabase.get_optimization_run(body.optimization_run_id, user_id)
        if not check_run:
            raise HTTPException(status_code=404, detail="Optimization run not found")
        _check_company_cap(profile, check_run, supabase, user_id)
        session = supabase.create_coach_session(user_id, body.optimization_run_id)
        optimization_run_id = body.optimization_run_id

    session_id = session["id"]

    # Load optimization run for context (already verified above for lazy path).
    run = supabase.get_optimization_run(optimization_run_id, user_id)
    if not run:
        raise HTTPException(status_code=404, detail="Optimization run not found")

    job_parsed = run.get("job_parsed") or {}

    # Load CV text
    cv_text = ""
    if run.get("cv_id"):
        cv = supabase.get_cv(run["cv_id"], user_id)
        if cv:
            cv_text = cv.get("content_text", "") or ""

    # Load message history
    raw_history = supabase.get_coach_messages(session_id)
    if raw_history:
        message_history = ModelMessagesTypeAdapter.validate_python(raw_history)
    else:
        message_history = None

    deps = CoachDeps(
        user_id=user_id,
        resume_text=cv_text,
        job_title=job_parsed.get("title", "Unknown"),
        job_company=job_parsed.get("company", "Unknown"),
        job_requirements=job_parsed.get("requirements", []),
        job_keywords=job_parsed.get("keywords", []),
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
                await asyncio.to_thread(supabase.save_coach_messages, session_id, serialized)

                # Send done event with thread_id
                done = json.dumps({"type": "done", "thread_id": session_id})
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
