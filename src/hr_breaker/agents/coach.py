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
    on_save_story: Any = None  # async callable

    model_config = {"arbitrary_types_allowed": True}


def _load_system_prompt() -> str:
    path = TEMPLATE_DIR / "coach_system.md"
    return path.read_text(encoding="utf-8")


def create_coach_agent() -> Agent:
    settings = get_settings()

    agent = Agent(
        f"google-gla:{settings.gemini_pro_model}",
        system_prompt=_load_system_prompt(),
        model_settings=get_model_settings(),
        deps_type=CoachDeps,
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
