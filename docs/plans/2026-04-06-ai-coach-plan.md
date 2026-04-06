# AI Interview Coach — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an AI interview coach chat with STAR methodology coaching and storybank to HR-Breaker.

**Architecture:** New Pydantic-AI agent with tools, FastAPI SSE streaming endpoint, Supabase tables for sessions/messages/storybank, Next.js chat UI with storybank panel. Uses `run_stream()` + manual SSE encoding for streaming, `ModelMessagesTypeAdapter` for message history serialization.

**Tech Stack:** Pydantic-AI (agent + streaming), FastAPI (SSE via StreamingResponse), Supabase (tables + storage), Next.js 16 (App Router), React Query, Tailwind CSS, Framer Motion, lucide-react.

**Design doc:** `docs/plans/2026-04-06-ai-coach-design.md`

---

### Task 1: Supabase Migration — Coach Tables

**Files:**
- Create: `supabase/migrations/008_coach_tables.sql`

**Step 1: Write migration SQL**

```sql
-- Coach sessions (one per user+optimization_run pair)
CREATE TABLE IF NOT EXISTS coach_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    optimization_run_id UUID NOT NULL REFERENCES optimization_runs(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, optimization_run_id)
);

CREATE INDEX IF NOT EXISTS idx_coach_sessions_user ON coach_sessions(user_id);

-- Coach messages (Pydantic-AI serialized format)
CREATE TABLE IF NOT EXISTS coach_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES coach_sessions(id) ON DELETE CASCADE,
    messages JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_coach_messages_session ON coach_messages(session_id);

-- Storybank entries (global per user)
CREATE TABLE IF NOT EXISTS storybank_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    situation TEXT NOT NULL DEFAULT '',
    task TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL DEFAULT '',
    tags TEXT[] NOT NULL DEFAULT '{}',
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_storybank_user ON storybank_entries(user_id);

-- Enable RLS
ALTER TABLE coach_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE coach_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE storybank_entries ENABLE ROW LEVEL SECURITY;

-- RLS policies (service key bypasses, but good practice)
CREATE POLICY coach_sessions_user ON coach_sessions FOR ALL USING (auth.uid() = user_id);
CREATE POLICY coach_messages_user ON coach_messages FOR ALL USING (
    session_id IN (SELECT id FROM coach_sessions WHERE user_id = auth.uid())
);
CREATE POLICY storybank_entries_user ON storybank_entries FOR ALL USING (auth.uid() = user_id);
```

**Step 2: Apply migration**

Run: `cd supabase && supabase db push` (or apply via Supabase dashboard SQL editor)

**Step 3: Commit**

```bash
git add supabase/migrations/008_coach_tables.sql
git commit -m "feat(coach): add Supabase migration for coach sessions, messages, and storybank"
```

---

### Task 2: Supabase Service — Coach & Storybank Methods

**Files:**
- Modify: `src/hr_breaker/services/supabase.py`

**Step 1: Add coach session methods to SupabaseService**

Add these methods after the existing optimization run methods (~line 318):

```python
    # Coach session operations
    def get_or_create_coach_session(
        self, user_id: str, optimization_run_id: str
    ) -> dict[str, Any]:
        """Get existing coach session or create new one."""
        try:
            result = (
                self._client.table("coach_sessions")
                .select("*")
                .eq("user_id", user_id)
                .eq("optimization_run_id", optimization_run_id)
                .maybe_single()
                .execute()
            )
            if result.data:
                return result.data

            # Create new session
            result = (
                self._client.table("coach_sessions")
                .insert({
                    "user_id": user_id,
                    "optimization_run_id": optimization_run_id,
                })
                .execute()
            )
            return result.data[0]
        except Exception as e:
            logger.error(f"Failed to get/create coach session: {e}")
            raise SupabaseError(f"Failed to get/create coach session: {e}") from e

    def list_coach_sessions(self, user_id: str) -> list[dict[str, Any]]:
        """List all coach sessions for a user."""
        try:
            result = (
                self._client.table("coach_sessions")
                .select("id, optimization_run_id, created_at, updated_at")
                .eq("user_id", user_id)
                .order("updated_at", desc=True)
                .execute()
            )
            return result.data
        except Exception as e:
            logger.error(f"Failed to list coach sessions: {e}")
            raise SupabaseError(f"Failed to list coach sessions: {e}") from e

    def get_coach_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Get serialized message history for a coach session."""
        try:
            result = (
                self._client.table("coach_messages")
                .select("messages, updated_at")
                .eq("session_id", session_id)
                .maybe_single()
                .execute()
            )
            if result.data:
                return result.data["messages"]
            return []
        except Exception as e:
            logger.error(f"Failed to get coach messages: {e}")
            raise SupabaseError(f"Failed to get coach messages: {e}") from e

    def save_coach_messages(self, session_id: str, messages: list) -> None:
        """Save (upsert) serialized message history for a coach session."""
        try:
            # Check if row exists
            existing = (
                self._client.table("coach_messages")
                .select("id")
                .eq("session_id", session_id)
                .maybe_single()
                .execute()
            )
            if existing.data:
                self._client.table("coach_messages").update({
                    "messages": messages,
                    "updated_at": datetime.now().isoformat(),
                }).eq("session_id", session_id).execute()
            else:
                self._client.table("coach_messages").insert({
                    "session_id": session_id,
                    "messages": messages,
                }).execute()

            # Touch session updated_at
            self._client.table("coach_sessions").update({
                "updated_at": datetime.now().isoformat(),
            }).eq("id", session_id).execute()
        except Exception as e:
            logger.error(f"Failed to save coach messages: {e}")
            raise SupabaseError(f"Failed to save coach messages: {e}") from e

    # Storybank operations
    def list_storybank(self, user_id: str) -> list[dict[str, Any]]:
        """List all storybank entries for a user."""
        try:
            result = (
                self._client.table("storybank_entries")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .execute()
            )
            return result.data
        except Exception as e:
            logger.error(f"Failed to list storybank: {e}")
            raise SupabaseError(f"Failed to list storybank: {e}") from e

    def create_storybank_entry(
        self, user_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a new storybank entry."""
        try:
            result = (
                self._client.table("storybank_entries")
                .insert({
                    "user_id": user_id,
                    **data,
                })
                .execute()
            )
            return result.data[0]
        except Exception as e:
            logger.error(f"Failed to create storybank entry: {e}")
            raise SupabaseError(f"Failed to create storybank entry: {e}") from e

    def update_storybank_entry(
        self, entry_id: str, user_id: str, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update a storybank entry (with ownership check)."""
        try:
            result = (
                self._client.table("storybank_entries")
                .update({**data, "updated_at": datetime.now().isoformat()})
                .eq("id", entry_id)
                .eq("user_id", user_id)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to update storybank entry: {e}")
            raise SupabaseError(f"Failed to update storybank entry: {e}") from e

    def delete_storybank_entry(self, entry_id: str, user_id: str) -> bool:
        """Delete a storybank entry (with ownership check)."""
        try:
            result = (
                self._client.table("storybank_entries")
                .delete()
                .eq("id", entry_id)
                .eq("user_id", user_id)
                .execute()
            )
            return bool(result.data)
        except Exception as e:
            logger.error(f"Failed to delete storybank entry: {e}")
            raise SupabaseError(f"Failed to delete storybank entry: {e}") from e
```

**Step 2: Commit**

```bash
git add src/hr_breaker/services/supabase.py
git commit -m "feat(coach): add Supabase service methods for coach sessions and storybank"
```

---

### Task 3: Coach System Prompt

**Files:**
- Create: `templates/coach_system.md`

**Step 1: Write the system prompt**

```markdown
You are an experienced career coach and interview preparation expert.

## Your Role
- Help users prepare for job interviews through mock questions, answer evaluation, and STAR methodology coaching
- Respond in the same language the user writes in
- Be specific: give concrete examples, formulations, and scores
- Don't initiate topics — react to user requests

## STAR Methodology
When evaluating interview answers, break them down into STAR components:
- **Situation** — context and background (should be concise, 1-2 sentences)
- **Task** — your specific responsibility or challenge
- **Action** — concrete steps YOU took (most important part, should be detailed)
- **Result** — measurable outcomes, impact, learnings

When an answer is weak, point out which component needs improvement and suggest a specific reformulation.

## Scoring Rubric (1-5 points per dimension)
When the user asks you to evaluate an answer or after a mock question, score on these 5 dimensions:

| Score | Substance | Structure | Relevance | Credibility | Differentiation |
|-------|-----------|-----------|-----------|-------------|-----------------|
| 1 | Vague, no details | No logical flow | Unrelated to role | Implausible claims | Generic, anyone could say this |
| 2 | Some details, surface-level | Partial structure | Tangentially related | Some gaps in logic | Slightly personal |
| 3 | Concrete examples | Clear STAR format | Matches key requirements | Believable, some metrics | Shows unique perspective |
| 4 | Rich detail, metrics | Polished STAR flow | Directly targets role needs | Strong evidence, numbers | Memorable insight |
| 5 | Exceptional depth | Masterful storytelling | Perfect role alignment | Irrefutable proof | "Earned secret" — only you could know this |

Present scores in a compact table after evaluation.

## Mock Questions
When generating interview questions:
- Base them on the job description requirements and keywords
- Mix behavioral ("Tell me about a time...") and situational ("What would you do if...")
- Start with common questions, progress to role-specific ones
- After the user answers, evaluate using the scoring rubric above

## Storybank
You have access to the user's storybank — a library of their career stories in STAR format.
- When the user shares a good story, suggest saving it with the `save_story` tool
- When preparing for a question, use `find_stories` to suggest relevant existing stories
- Help users improve weak stories (rating < 3) by asking probing questions about Actions and Results

## Tools
- `save_story` — save a new STAR story to the user's storybank. Use when a user shares a well-structured story worth reusing.
- `list_stories` — show all stories in the storybank. Use when user asks to see their stories.
- `find_stories` — find stories matching a theme/competency. Use when helping user pick stories for specific questions.

## Context
You have access to:
- The user's resume (original content)
- The job description (parsed: title, company, requirements, keywords)
- The user's storybank (all saved stories)

Use this context to tailor questions, evaluate relevance, and suggest which experiences to highlight.
```

**Step 2: Commit**

```bash
git add templates/coach_system.md
git commit -m "feat(coach): add system prompt for interview coach agent"
```

---

### Task 4: Coach Agent with Tools

**Files:**
- Create: `src/hr_breaker/agents/coach.py`

**Step 1: Write the coach agent**

```python
"""Interview coach agent with STAR methodology and storybank tools."""

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

from hr_breaker.config import get_model_settings, get_settings

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent.parent.parent.parent / "templates"


class CoachDeps(BaseModel):
    """Dependencies injected into the coach agent."""
    user_id: str
    resume_text: str
    job_title: str
    job_company: str
    job_requirements: list[str]
    job_keywords: list[str]
    storybank: list[dict[str, Any]]
    # Callback to persist storybank entries
    on_save_story: Any = None  # async callable

    model_config = {"arbitrary_types_allowed": True}


def _load_system_prompt() -> str:
    """Load the coach system prompt from template."""
    path = TEMPLATE_DIR / "coach_system.md"
    return path.read_text(encoding="utf-8")


def create_coach_agent() -> Agent:
    """Create the interview coach agent."""
    settings = get_settings()

    agent = Agent(
        f"google-gla:{settings.gemini_pro_model}",
        system_prompt=_load_system_prompt(),
        model_settings=get_model_settings(),
    )

    @agent.system_prompt
    async def add_context(ctx: RunContext[CoachDeps]) -> str:
        deps = ctx.deps
        parts = [
            f"## Current Position\n**{deps.job_title}** at **{deps.job_company}**",
            f"### Key Requirements\n" + "\n".join(f"- {r}" for r in deps.job_requirements),
            f"### Keywords\n{', '.join(deps.job_keywords)}",
            f"## User's Resume\n{deps.resume_text[:3000]}",
        ]
        if deps.storybank:
            stories = []
            for s in deps.storybank:
                tags = ", ".join(s.get("tags", []))
                rating = f" (rating: {s['rating']}/5)" if s.get("rating") else ""
                stories.append(
                    f"### {s['title']}{rating}\n"
                    f"Tags: {tags}\n"
                    f"- S: {s['situation']}\n- T: {s['task']}\n"
                    f"- A: {s['action']}\n- R: {s['result']}"
                )
            parts.append("## User's Storybank\n" + "\n\n".join(stories))
        else:
            parts.append("## User's Storybank\nNo stories saved yet.")
        return "\n\n".join(parts)

    @agent.tool
    async def save_story(
        ctx: RunContext[CoachDeps],
        title: str,
        situation: str,
        task: str,
        action: str,
        result: str,
        tags: list[str],
    ) -> str:
        """Save a new STAR story to the user's storybank."""
        if ctx.deps.on_save_story:
            entry = await ctx.deps.on_save_story({
                "title": title,
                "situation": situation,
                "task": task,
                "action": action,
                "result": result,
                "tags": tags,
            })
            return f"Story '{title}' saved to storybank (id: {entry['id']})"
        return f"Story '{title}' noted (storybank save unavailable)"

    @agent.tool
    async def list_stories(ctx: RunContext[CoachDeps]) -> str:
        """List all stories in the user's storybank."""
        if not ctx.deps.storybank:
            return "No stories in storybank yet."
        lines = []
        for s in ctx.deps.storybank:
            tags = ", ".join(s.get("tags", []))
            rating = f" [{s['rating']}/5]" if s.get("rating") else ""
            lines.append(f"- **{s['title']}**{rating} ({tags})")
        return "\n".join(lines)

    @agent.tool
    async def find_stories(ctx: RunContext[CoachDeps], theme: str) -> str:
        """Find stories matching a theme or competency keyword."""
        theme_lower = theme.lower()
        matches = []
        for s in ctx.deps.storybank:
            searchable = f"{s['title']} {' '.join(s.get('tags', []))} {s['situation']} {s['action']}".lower()
            if theme_lower in searchable:
                matches.append(s)
        if not matches:
            return f"No stories found matching '{theme}'. Consider creating one."
        lines = []
        for s in matches:
            lines.append(
                f"### {s['title']}\n- S: {s['situation']}\n- T: {s['task']}\n"
                f"- A: {s['action']}\n- R: {s['result']}"
            )
        return "\n\n".join(lines)

    return agent
```

**Step 2: Commit**

```bash
git add src/hr_breaker/agents/coach.py
git commit -m "feat(coach): add Pydantic-AI coach agent with STAR tools"
```

---

### Task 5: Backend API — Coach Routes

**Files:**
- Create: `src/hr_breaker/api/routes/coach.py`
- Modify: `src/hr_breaker/api/routes/__init__.py`
- Modify: `src/hr_breaker/api/main.py`
- Modify: `src/hr_breaker/api/schemas.py`

**Step 1: Add schemas to `schemas.py`**

Add at end of file:

```python
class CoachChatRequest(BaseModel):
    """Request to send a message to the coach."""
    session_id: str | None = None  # None = auto-create from optimization_run_id
    optimization_run_id: str
    message: str

class CoachSessionResponse(BaseModel):
    """Coach session info."""
    id: str
    optimization_run_id: str
    created_at: str
    updated_at: str

class CoachMessageResponse(BaseModel):
    """Coach message for display."""
    role: str  # "user" | "assistant"
    content: str
    created_at: str | None = None

class StorybankEntryRequest(BaseModel):
    """Request to create/update a storybank entry."""
    title: str
    situation: str = ""
    task: str = ""
    action: str = ""
    result: str = ""
    tags: list[str] = []
    rating: int | None = None

class StorybankEntryResponse(BaseModel):
    """Storybank entry."""
    id: str
    title: str
    situation: str
    task: str
    action: str
    result: str
    tags: list[str]
    rating: int | None
    created_at: str
    updated_at: str
```

**Step 2: Write the coach routes**

Create `src/hr_breaker/api/routes/coach.py`:

```python
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
    sessions = supabase.list_coach_sessions(user_id)
    return sessions


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
```

**Step 3: Register the router**

In `src/hr_breaker/api/routes/__init__.py`, add:

```python
from .coach import router as coach_router
```

and add `"coach_router"` to `__all__`.

In `src/hr_breaker/api/main.py`, add:

```python
from hr_breaker.api.routes import coach_router
```

and:

```python
app.include_router(coach_router, prefix="/api/coach", tags=["coach"])
```

**Step 4: Commit**

```bash
git add src/hr_breaker/api/routes/coach.py src/hr_breaker/api/routes/__init__.py src/hr_breaker/api/main.py src/hr_breaker/api/schemas.py
git commit -m "feat(coach): add FastAPI routes for coach chat SSE and storybank CRUD"
```

---

### Task 6: Frontend Types & API Client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`

**Step 1: Add TypeScript types**

Add to `frontend/src/types/index.ts`:

```typescript
// Coach types
export interface CoachSession {
  id: string;
  optimization_run_id: string;
  created_at: string;
  updated_at: string;
}

export interface CoachMessage {
  role: "user" | "assistant";
  content: string;
}

export interface CoachChatRequest {
  optimization_run_id: string;
  message: string;
  session_id?: string;
}

export interface CoachSSEEvent {
  type: "delta" | "done" | "error";
  content?: string;
  session_id?: string;
}

// Storybank types
export interface StorybankEntry {
  id: string;
  title: string;
  situation: string;
  task: string;
  action: string;
  result: string;
  tags: string[];
  rating: number | null;
  created_at: string;
  updated_at: string;
}

export interface StorybankEntryRequest {
  title: string;
  situation?: string;
  task?: string;
  action?: string;
  result?: string;
  tags?: string[];
  rating?: number | null;
}
```

**Step 2: Add API functions**

Add to `frontend/src/lib/api.ts`:

```typescript
import type { CoachSession, CoachMessage, StorybankEntry, StorybankEntryRequest } from "@/types";

// Coach API
export async function listCoachSessions(): Promise<CoachSession[]> {
  return fetchWithAuth<CoachSession[]>("/coach/sessions");
}

export async function getCoachMessages(sessionId: string): Promise<CoachMessage[]> {
  return fetchWithAuth<CoachMessage[]>(`/coach/sessions/${sessionId}/messages`);
}

export async function streamCoachChat(
  optimizationRunId: string,
  message: string,
  sessionId?: string,
  onDelta: (text: string) => void = () => {},
  onDone: (sessionId: string) => void = () => {},
  onError: (error: string) => void = () => {},
): Promise<void> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE}/coach/chat`, {
    method: "POST",
    headers: {
      ...headers,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      optimization_run_id: optimizationRunId,
      message,
      session_id: sessionId,
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Chat failed: ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          const event = JSON.parse(line.slice(6));
          if (event.type === "delta") onDelta(event.content || "");
          else if (event.type === "done") onDone(event.session_id || "");
          else if (event.type === "error") onError(event.content || "Unknown error");
        } catch {
          // skip malformed events
        }
      }
    }
  }
}

// Storybank API
export async function listStorybank(): Promise<StorybankEntry[]> {
  return fetchWithAuth<StorybankEntry[]>("/coach/storybank");
}

export async function createStorybankEntry(data: StorybankEntryRequest): Promise<StorybankEntry> {
  return fetchWithAuth<StorybankEntry>("/coach/storybank", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateStorybankEntry(id: string, data: StorybankEntryRequest): Promise<StorybankEntry> {
  return fetchWithAuth<StorybankEntry>(`/coach/storybank/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deleteStorybankEntry(id: string): Promise<void> {
  await fetchWithAuth(`/coach/storybank/${id}`, { method: "DELETE" });
}
```

**Step 3: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/api.ts
git commit -m "feat(coach): add frontend types and API client for coach and storybank"
```

---

### Task 7: Frontend Hooks — useCoach & useStorybank

**Files:**
- Create: `frontend/src/hooks/useCoach.ts`
- Create: `frontend/src/hooks/useStorybank.ts`

**Step 1: Write useCoach hook**

```typescript
"use client";

import { useState, useCallback, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  listCoachSessions,
  getCoachMessages,
  streamCoachChat,
} from "@/lib/api";
import type { CoachMessage, CoachSession } from "@/types";

export function useCoachSessions() {
  return useQuery<CoachSession[]>({
    queryKey: ["coach-sessions"],
    queryFn: listCoachSessions,
    staleTime: 60_000,
  });
}

export function useCoachMessages(sessionId: string | null) {
  return useQuery<CoachMessage[]>({
    queryKey: ["coach-messages", sessionId],
    queryFn: () => getCoachMessages(sessionId!),
    enabled: !!sessionId,
    staleTime: 30_000,
  });
}

export function useCoachChat() {
  const [messages, setMessages] = useState<CoachMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const abortRef = useRef(false);

  const loadHistory = useCallback((history: CoachMessage[]) => {
    setMessages(history);
  }, []);

  const sendMessage = useCallback(
    async (optimizationRunId: string, content: string) => {
      if (isStreaming) return;

      const userMsg: CoachMessage = { role: "user", content };
      setMessages((prev) => [...prev, userMsg]);
      setIsStreaming(true);
      abortRef.current = false;

      // Add empty assistant message for streaming
      const assistantMsg: CoachMessage = { role: "assistant", content: "" };
      setMessages((prev) => [...prev, assistantMsg]);

      try {
        await streamCoachChat(
          optimizationRunId,
          content,
          sessionId ?? undefined,
          // onDelta
          (delta) => {
            if (abortRef.current) return;
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last.role === "assistant") {
                updated[updated.length - 1] = {
                  ...last,
                  content: last.content + delta,
                };
              }
              return updated;
            });
          },
          // onDone
          (newSessionId) => {
            setSessionId(newSessionId);
            setIsStreaming(false);
          },
          // onError
          (error) => {
            setMessages((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = {
                role: "assistant",
                content: `Error: ${error}`,
              };
              return updated;
            });
            setIsStreaming(false);
          }
        );
      } catch (e) {
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            role: "assistant",
            content: `Error: ${e instanceof Error ? e.message : "Unknown error"}`,
          };
          return updated;
        });
        setIsStreaming(false);
      }
    },
    [isStreaming, sessionId]
  );

  const resetChat = useCallback(() => {
    setMessages([]);
    setSessionId(null);
    abortRef.current = true;
    setIsStreaming(false);
  }, []);

  return {
    messages,
    isStreaming,
    sessionId,
    sendMessage,
    loadHistory,
    resetChat,
    setSessionId,
  };
}
```

**Step 2: Write useStorybank hook**

```typescript
"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listStorybank,
  createStorybankEntry,
  updateStorybankEntry,
  deleteStorybankEntry,
} from "@/lib/api";
import type { StorybankEntry, StorybankEntryRequest } from "@/types";

export function useStorybank() {
  return useQuery<StorybankEntry[]>({
    queryKey: ["storybank"],
    queryFn: listStorybank,
    staleTime: 30_000,
  });
}

export function useCreateStory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: StorybankEntryRequest) => createStorybankEntry(data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["storybank"] }),
  });
}

export function useUpdateStory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: StorybankEntryRequest }) =>
      updateStorybankEntry(id, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["storybank"] }),
  });
}

export function useDeleteStory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteStorybankEntry(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["storybank"] }),
  });
}
```

**Step 3: Commit**

```bash
git add frontend/src/hooks/useCoach.ts frontend/src/hooks/useStorybank.ts
git commit -m "feat(coach): add useCoach and useStorybank hooks"
```

---

### Task 8: Frontend — Storybank Panel Component

**Files:**
- Create: `frontend/src/components/StorybankPanel.tsx`

**Step 1: Write the component**

```tsx
"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "@/components/motion";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  BookOpen,
  ChevronRight,
  Pencil,
  Trash2,
  X,
  Check,
  Star,
} from "lucide-react";
import { useStorybank, useUpdateStory, useDeleteStory } from "@/hooks/useStorybank";
import type { StorybankEntry, StorybankEntryRequest } from "@/types";
import { cn } from "@/lib/utils";

function StoryCard({
  story,
  onUpdate,
  onDelete,
}: {
  story: StorybankEntry;
  onUpdate: (data: StorybankEntryRequest) => void;
  onDelete: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editData, setEditData] = useState<StorybankEntryRequest>({
    title: story.title,
    situation: story.situation,
    task: story.task,
    action: story.action,
    result: story.result,
    tags: story.tags,
    rating: story.rating,
  });

  const handleSave = () => {
    onUpdate(editData);
    setEditing(false);
  };

  if (editing) {
    return (
      <div className="rounded-lg border border-border bg-card p-3 space-y-2">
        <input
          className="w-full rounded border border-border bg-background px-2 py-1 text-sm"
          value={editData.title}
          onChange={(e) => setEditData({ ...editData, title: e.target.value })}
          placeholder="Title"
        />
        {(["situation", "task", "action", "result"] as const).map((field) => (
          <textarea
            key={field}
            className="w-full rounded border border-border bg-background px-2 py-1 text-sm resize-none"
            rows={2}
            value={editData[field] || ""}
            onChange={(e) => setEditData({ ...editData, [field]: e.target.value })}
            placeholder={field.charAt(0).toUpperCase() + field.slice(1)}
          />
        ))}
        <input
          className="w-full rounded border border-border bg-background px-2 py-1 text-sm"
          value={editData.tags?.join(", ") || ""}
          onChange={(e) =>
            setEditData({
              ...editData,
              tags: e.target.value.split(",").map((t) => t.trim()).filter(Boolean),
            })
          }
          placeholder="Tags (comma-separated)"
        />
        <div className="flex gap-1">
          <Button size="sm" variant="ghost" onClick={handleSave}>
            <Check className="h-3 w-3" />
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
            <X className="h-3 w-3" />
          </Button>
        </div>
      </div>
    );
  }

  return (
    <motion.div
      layout
      className="rounded-lg border border-border bg-card overflow-hidden"
    >
      <button
        className="w-full p-3 text-left flex items-start gap-2 hover:bg-secondary/50 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <ChevronRight
          className={cn(
            "h-4 w-4 mt-0.5 shrink-0 transition-transform",
            expanded && "rotate-90"
          )}
        />
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium truncate">{story.title}</div>
          <div className="flex flex-wrap gap-1 mt-1">
            {story.tags.map((tag) => (
              <Badge key={tag} variant="secondary" className="text-[10px] px-1.5 py-0">
                {tag}
              </Badge>
            ))}
            {story.rating && (
              <span className="flex items-center gap-0.5 text-[10px] text-muted-foreground">
                <Star className="h-2.5 w-2.5 fill-current" />
                {story.rating}
              </span>
            )}
          </div>
        </div>
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="px-3 pb-3 space-y-1.5 text-xs text-muted-foreground">
              <p><span className="font-medium text-foreground">S:</span> {story.situation}</p>
              <p><span className="font-medium text-foreground">T:</span> {story.task}</p>
              <p><span className="font-medium text-foreground">A:</span> {story.action}</p>
              <p><span className="font-medium text-foreground">R:</span> {story.result}</p>
              <div className="flex gap-1 pt-1">
                <Button size="sm" variant="ghost" className="h-6 px-2" onClick={() => setEditing(true)}>
                  <Pencil className="h-3 w-3" />
                </Button>
                <Button size="sm" variant="ghost" className="h-6 px-2 text-destructive" onClick={onDelete}>
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export function StorybankPanel({
  collapsed,
  onToggle,
}: {
  collapsed: boolean;
  onToggle: () => void;
}) {
  const { data: stories = [], isLoading } = useStorybank();
  const updateMutation = useUpdateStory();
  const deleteMutation = useDeleteStory();

  if (collapsed) {
    return (
      <Button
        variant="ghost"
        size="icon"
        className="fixed right-4 top-20 z-40"
        onClick={onToggle}
      >
        <BookOpen className="h-4 w-4" />
      </Button>
    );
  }

  return (
    <div className="flex h-full w-full flex-col border-l border-border bg-background">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4" />
          <span className="text-sm font-medium">Storybank</span>
          <Badge variant="secondary" className="text-[10px]">
            {stories.length}
          </Badge>
        </div>
        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onToggle}>
          <X className="h-3 w-3" />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {isLoading ? (
          <div className="text-xs text-muted-foreground text-center py-8">Loading...</div>
        ) : stories.length === 0 ? (
          <div className="text-xs text-muted-foreground text-center py-8">
            No stories yet. Chat with the coach to build your storybank.
          </div>
        ) : (
          stories.map((story) => (
            <StoryCard
              key={story.id}
              story={story}
              onUpdate={(data) => updateMutation.mutate({ id: story.id, data })}
              onDelete={() => deleteMutation.mutate(story.id)}
            />
          ))
        )}
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/StorybankPanel.tsx
git commit -m "feat(coach): add StorybankPanel component"
```

---

### Task 9: Frontend — Chat Component

**Files:**
- Create: `frontend/src/components/CoachChat.tsx`

**Step 1: Write the chat component**

```tsx
"use client";

import { useState, useRef, useEffect } from "react";
import { motion } from "@/components/motion";
import { Button } from "@/components/ui/button";
import { Send, Loader2 } from "lucide-react";
import type { CoachMessage } from "@/types";
import { cn } from "@/lib/utils";

function MessageBubble({ message }: { message: CoachMessage }) {
  const isUser = message.role === "user";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn("flex", isUser ? "justify-end" : "justify-start")}
    >
      <div
        className={cn(
          "max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-secondary text-secondary-foreground"
        )}
      >
        <div className="whitespace-pre-wrap break-words">{message.content}</div>
      </div>
    </motion.div>
  );
}

export function CoachChat({
  messages,
  isStreaming,
  onSend,
}: {
  messages: CoachMessage[];
  isStreaming: boolean;
  onSend: (message: string) => void;
}) {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = () => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;
    onSend(trimmed);
    setInput("");
    // Reset textarea height
    if (inputRef.current) inputRef.current.style.height = "auto";
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    // Auto-resize
    const target = e.target;
    target.style.height = "auto";
    target.style.height = Math.min(target.scrollHeight, 120) + "px";
  };

  return (
    <div className="flex h-full flex-col">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {messages.length === 0 && (
          <div className="flex h-full items-center justify-center">
            <div className="text-center text-muted-foreground">
              <p className="text-lg font-medium">Interview Coach</p>
              <p className="text-sm mt-1">
                Ask me to generate mock questions, evaluate your answers, or help build your storybank.
              </p>
            </div>
          </div>
        )}
        {messages.map((msg, i) => (
          <MessageBubble key={i} message={msg} />
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-border bg-background px-4 py-3">
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Ask the coach..."
            rows={1}
            className="flex-1 resize-none rounded-xl border border-border bg-secondary/50 px-4 py-2.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            disabled={isStreaming}
          />
          <Button
            size="icon"
            className="h-10 w-10 shrink-0 rounded-xl"
            onClick={handleSubmit}
            disabled={!input.trim() || isStreaming}
          >
            {isStreaming ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/CoachChat.tsx
git commit -m "feat(coach): add CoachChat component with streaming support"
```

---

### Task 10: Frontend — Coach Page

**Files:**
- Create: `frontend/src/app/(protected)/coach/page.tsx`
- Modify: `frontend/src/components/Navbar.tsx`

**Step 1: Write the coach page**

```tsx
"use client";

import { useState, useEffect } from "react";
import { motion } from "@/components/motion";
import { CoachChat } from "@/components/CoachChat";
import { StorybankPanel } from "@/components/StorybankPanel";
import { useCoachChat, useCoachMessages } from "@/hooks/useCoach";
import { useStorybank } from "@/hooks/useStorybank";
import { useQuery } from "@tanstack/react-query";
import { listOptimizations } from "@/lib/api";
import type { OptimizationSummary } from "@/types";

export default function CoachPage() {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [storybankCollapsed, setStorybankCollapsed] = useState(false);

  const { data: optimizations = [] } = useQuery<OptimizationSummary[]>({
    queryKey: ["optimizations"],
    queryFn: listOptimizations,
    staleTime: 60_000,
  });

  // Only completed optimizations with parsed job data
  const positions = optimizations.filter(
    (o) => o.status === "complete" && o.job_title
  );

  const {
    messages,
    isStreaming,
    sessionId,
    sendMessage,
    loadHistory,
    resetChat,
    setSessionId,
  } = useCoachChat();

  // Load existing messages when session changes
  const { data: history } = useCoachMessages(sessionId);
  useEffect(() => {
    if (history && history.length > 0) {
      loadHistory(history);
    }
  }, [history, loadHistory]);

  // Reset chat when position changes
  const handlePositionChange = (runId: string) => {
    setSelectedRunId(runId);
    resetChat();
  };

  const handleSend = (content: string) => {
    if (!selectedRunId) return;
    sendMessage(selectedRunId, content);
  };

  // Refetch storybank after streaming completes (coach may have saved stories)
  const { refetch: refetchStorybank } = useStorybank();
  useEffect(() => {
    if (!isStreaming && sessionId) {
      refetchStorybank();
    }
  }, [isStreaming, sessionId, refetchStorybank]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="mx-auto flex h-[calc(100vh-4rem)] max-w-7xl"
    >
      {/* Chat area */}
      <div className="flex flex-1 flex-col">
        {/* Position selector */}
        <div className="border-b border-border px-4 py-3">
          <select
            value={selectedRunId || ""}
            onChange={(e) => handlePositionChange(e.target.value)}
            className="w-full max-w-md rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
          >
            <option value="" disabled>
              Select a position...
            </option>
            {positions.map((p) => (
              <option key={p.id} value={p.id}>
                {p.job_company} — {p.job_title}
              </option>
            ))}
          </select>
        </div>

        {/* Chat */}
        {selectedRunId ? (
          <CoachChat
            messages={messages}
            isStreaming={isStreaming}
            onSend={handleSend}
          />
        ) : (
          <div className="flex flex-1 items-center justify-center text-muted-foreground">
            <p className="text-sm">Select a position to start coaching</p>
          </div>
        )}
      </div>

      {/* Storybank panel */}
      <div
        className={
          storybankCollapsed ? "hidden" : "hidden w-80 shrink-0 lg:block"
        }
      >
        <StorybankPanel
          collapsed={storybankCollapsed}
          onToggle={() => setStorybankCollapsed(!storybankCollapsed)}
        />
      </div>
      {storybankCollapsed && (
        <StorybankPanel
          collapsed={true}
          onToggle={() => setStorybankCollapsed(false)}
        />
      )}
    </motion.div>
  );
}
```

**Step 2: Add Coach tab to Navbar**

In `frontend/src/components/Navbar.tsx`, change the `navItems` array (line 11-15):

```typescript
const navItems = [
  { href: "/optimize", label: "Optimize", icon: Sparkles },
  { href: "/cvs", label: "CVs", icon: FileText },
  { href: "/coach", label: "Coach", icon: MessageCircle },
  { href: "/history", label: "History", icon: History },
];
```

Add `MessageCircle` to the lucide-react imports:

```typescript
import { LogOut, Settings, Sparkles, FileText, History, MessageCircle } from "lucide-react";
```

**Step 3: Commit**

```bash
git add frontend/src/app/(protected)/coach/page.tsx frontend/src/components/Navbar.tsx
git commit -m "feat(coach): add Coach page and navbar tab"
```

---

### Task 11: Integration Test — Smoke Test

**Files:**
- Create: `tests/test_coach_api.py`

**Step 1: Write a basic integration test**

```python
"""Smoke tests for coach API endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client with mocked auth."""
    with patch("hr_breaker.api.deps.get_current_user", return_value="test-user-id"):
        from hr_breaker.api.main import app
        yield TestClient(app)


@pytest.fixture
def mock_supabase():
    """Mock Supabase service."""
    with patch("hr_breaker.api.routes.coach.SupabaseServiceDep") as mock:
        service = MagicMock()
        service.list_coach_sessions.return_value = []
        service.list_storybank.return_value = []
        service.create_storybank_entry.return_value = {
            "id": "test-id",
            "title": "Test Story",
            "situation": "s",
            "task": "t",
            "action": "a",
            "result": "r",
            "tags": ["test"],
            "rating": None,
            "created_at": "2026-04-06T00:00:00Z",
            "updated_at": "2026-04-06T00:00:00Z",
        }
        mock.return_value = service
        yield service


def test_list_sessions(client, mock_supabase):
    """GET /api/coach/sessions returns empty list."""
    response = client.get("/api/coach/sessions")
    assert response.status_code == 200
    assert response.json() == []


def test_list_storybank(client, mock_supabase):
    """GET /api/coach/storybank returns empty list."""
    response = client.get("/api/coach/storybank")
    assert response.status_code == 200
    assert response.json() == []


def test_create_storybank_entry(client, mock_supabase):
    """POST /api/coach/storybank creates entry."""
    response = client.post(
        "/api/coach/storybank",
        json={
            "title": "Test Story",
            "situation": "s",
            "task": "t",
            "action": "a",
            "result": "r",
            "tags": ["test"],
        },
    )
    assert response.status_code == 201
    assert response.json()["title"] == "Test Story"
```

**Step 2: Run tests**

Run: `uv run pytest tests/test_coach_api.py -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/test_coach_api.py
git commit -m "test(coach): add smoke tests for coach API"
```

---

### Task 12: Manual E2E Verification

**Step 1: Apply the Supabase migration**

Run migration via Supabase dashboard SQL editor or CLI.

**Step 2: Start the backend**

Run: `uv run uvicorn hr_breaker.api.main:app --reload`
Verify: `GET http://localhost:8000/api/coach/sessions` returns `[]` (with valid auth token)

**Step 3: Start the frontend**

Run: `cd frontend && npm run dev`
Verify:
- Coach tab visible in navbar
- Clicking Coach shows position dropdown
- Selecting a completed optimization shows chat interface
- Storybank panel visible on desktop

**Step 4: Test chat streaming**

- Select a position
- Type "What interview questions should I expect?"
- Verify: response streams in token-by-token
- Verify: no errors in browser console or backend logs

**Step 5: Test storybank**

- Ask coach to save a story
- Verify: card appears in storybank panel
- Edit and delete story from panel

**Step 6: Final commit**

```bash
git add -A
git commit -m "feat(coach): AI interview coach with STAR coaching and storybank - complete MVP"
```
