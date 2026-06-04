"""Interview coach agent with STAR methodology."""

import logging
from pathlib import Path

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


def _load_system_prompt() -> str:
    path = TEMPLATE_DIR / "coach_system.md"
    return path.read_text(encoding="utf-8")


def create_coach_agent() -> Agent:
    settings = get_settings()

    agent = Agent(
        f"google-vertex:{settings.gemini_pro_model}",
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
        return "\n\n".join(parts)

    return agent
