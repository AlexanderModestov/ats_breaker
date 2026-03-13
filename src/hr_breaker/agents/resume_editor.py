"""Agent for editing resumes via LLM-generated patches."""

from __future__ import annotations

from pydantic_ai import Agent

from hr_breaker.config import get_model_settings, get_settings
from hr_breaker.models.editor import EditResult

_SYSTEM_PROMPT = """\
You are a resume editor. You receive:
1. Current HTML resume
2. The user's original resume text (source of truth — never fabricate)
3. An editing instruction

Return JSON patches to apply to the HTML. Each patch has:
- selector: CSS selector targeting the element (use IDs like #summary, #skills-list, #experience-item-0)
- action: "replace" | "append" | "prepend" | "remove"
- html: new HTML content (null for remove)

Rules:
- ONLY use information from the original resume. Never invent skills, companies, metrics.
- Make MINIMAL changes — only what the instruction asks for.
- Keep the same HTML structure and CSS classes.
- Provide brief reasoning for your changes.
"""


async def edit_resume(html: str, original_resume: str, instruction: str) -> EditResult:
    """Edit resume HTML based on instruction, returning patches."""
    settings = get_settings()
    agent = Agent(
        f"google-gla:{settings.gemini_flash_model}",
        system_prompt=_SYSTEM_PROMPT,
        output_type=EditResult,
        model_settings=get_model_settings(),
    )
    prompt = f"""## Current HTML Resume
```html
{html}
```

## Original Resume (source of truth)
```
{original_resume}
```

## Instruction
{instruction}
"""
    result = await agent.run(prompt)
    return result.output
