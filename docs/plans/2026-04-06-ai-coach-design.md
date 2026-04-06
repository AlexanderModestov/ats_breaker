# AI Interview Coach — Design Document

## Overview

AI-powered interview coach integrated into HR-Breaker as a new "Coach" tab. Chat-based interface where users practice interview answers, get STAR-methodology coaching, and build a reusable storybank.

## Scope (MVP)

- **Mock questions** — coach generates probable interview questions based on job description, evaluates user answers
- **STAR coaching** — helps reformulate answers into Situation-Task-Action-Result format, scores each component
- **Storybank** — persistent library of STAR stories with tags and ratings, reusable across positions

## Architecture

### Frontend

New tab "Coach" in top navbar, route `/coach` inside `(protected)` group.

**Layout:** two-column flex container.

**Left column — Chat (70% width):**
- Top: dropdown to select position (company + role, from saved optimizations)
- Message area: scrollable list, user messages right-aligned, coach left-aligned. Markdown rendering for coach responses (score tables, STAR markup)
- Bottom: text input + send button. During streaming — coach response appears token-by-token, send button disabled

**Right column — Storybank (30% width):**
- Header "Storybank" + collapse button
- List of story cards: title, tags (colored badges), rating (if set)
- Click card to expand STAR content
- Edit (inline form) and delete buttons
- When coach saves a story via tool — card appears in panel in real-time

**Mobile:** Storybank hides behind a drawer button, chat takes 100%.

**Streaming:** `fetch` + `ReadableStream` to consume SSE. Tokens appended to current message.

### Backend

**New agent** `coach` (`src/hr_breaker/agents/coach.py`) — Pydantic-AI agent with Gemini.

**API endpoints** (`src/hr_breaker/api/`):

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/coach/chat` | SSE stream, accepts message + session_id |
| GET | `/api/coach/sessions` | List user's chat sessions |
| GET | `/api/coach/sessions/{id}/messages` | Message history |
| GET | `/api/storybank` | All user's stories |
| PUT | `/api/storybank/{id}` | Edit story |
| DELETE | `/api/storybank/{id}` | Delete story |

**Streaming:** FastAPI `StreamingResponse` with `text/event-stream`. Agent streams tokens via `agent.run_stream()`, each chunk is an SSE event. On completion — full response saved to DB.

### Data Models (PostgreSQL)

**Table `coach_sessions`:**
- `id` (UUID, PK)
- `user_id` (FK -> users)
- `job_position_id` (FK -> saved positions/optimizations)
- `created_at`, `updated_at`

**Table `coach_messages`:**
- `id` (UUID, PK)
- `session_id` (FK -> coach_sessions)
- `role` (enum: user | assistant)
- `content` (text)
- `created_at`

**Table `storybank_entries`:**
- `id` (UUID, PK)
- `user_id` (FK -> users)
- `title` (varchar)
- `situation` (text)
- `task` (text)
- `action` (text)
- `result` (text)
- `tags` (text[] — PostgreSQL array)
- `rating` (integer 1-5, nullable — coach can rate)
- `created_at`, `updated_at`

**Relationships:** Storybank is not tied to a position — stories are global per user. Chat session is tied to a specific position. Switching positions creates or loads the corresponding session.

**Agent context:** each chat request loads last N messages from `coach_messages` + all user's `storybank_entries` (so coach can reference stories).

### System Prompt

Stored in `templates/coach_system.md`. Assembled dynamically from:

**Role and behavior:**
- Experienced career coach and interview expert
- Respond in user's language
- Don't initiate — react to requests
- Be specific: give examples, formulations, scores

**STAR methodology:**
- When evaluating answers, break down into S/T/A/R components
- Point out weaknesses: "Situation too long, Action not specific"
- Suggest reformulations

**Scoring (5 criteria, 1-5 points):**
- Substance — depth and specifics
- Structure — logic and STAR format
- Relevance — match to job description
- Credibility — plausibility, metrics
- Differentiation — uniqueness of experience

**Dynamic context (injected per request):**
- User's resume
- Parsed job description (title, company, requirements, keywords)
- User's storybank (all stories)

**Agent tools:**
- `save_story(title, situation, task, action, result, tags)` — save new story
- `list_stories()` — return all stories
- `find_stories(theme)` — find relevant stories by theme

## Future Expansion

Full career coaching system: kickoff onboarding, 8-stage drill progression with gating, transcript analysis, post-interview debrief, salary negotiation, calibration engine, LinkedIn/resume optimization.

## Reference

Inspired by [interview-coach-skill](https://github.com/noamseg/interview-coach-skill).
