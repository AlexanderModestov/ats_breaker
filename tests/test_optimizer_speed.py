"""Optimizer speed-ups: separate OPTIMIZER_MODEL role and a bounded tool loop."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from hr_breaker.config import get_settings
from hr_breaker.llm import validate_llm_config
from hr_breaker.models import JobPosting, ResumeSource


@pytest.fixture
def source():
    return ResumeSource(content="Python developer with 5 years experience")


@pytest.fixture
def job():
    return JobPosting(
        title="Senior Python Developer",
        company="Acme",
        requirements=["Python"],
        keywords=["python"],
    )


# --- A: OPTIMIZER_MODEL role ---

def test_validate_llm_config_checks_optimizer_model(monkeypatch):
    monkeypatch.setenv("OPTIMIZER_MODEL", "anthropic:claude-sonnet-5-5")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="OPTIMIZER_MODEL"):
            validate_llm_config()
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize("module,factory", [
    ("hr_breaker.agents.optimizer_v2", "get_optimizer_v2_agent"),
    ("hr_breaker.agents.optimizer", "get_optimizer_agent"),
])
def test_optimizer_agents_use_optimizer_model(monkeypatch, source, job, module, factory):
    import importlib
    monkeypatch.setenv("OPTIMIZATION_MODEL", "anthropic:claude-sonnet-5-5")
    monkeypatch.setenv("OPTIMIZER_MODEL", "google-gla:gemini-2.5-flash")
    get_settings.cache_clear()
    mod = importlib.import_module(module)
    try:
        with patch.object(mod, "build_model", wraps=mod.build_model) as spy:
            getattr(mod, factory)(job, source)
        spy.assert_called_once_with("google-gla:gemini-2.5-flash", env_var="OPTIMIZER_MODEL")
    finally:
        get_settings.cache_clear()


def test_other_agents_keep_optimization_model(monkeypatch):
    from hr_breaker.agents import auditor
    monkeypatch.setenv("OPTIMIZATION_MODEL", "anthropic:claude-sonnet-5-5")
    monkeypatch.setenv("OPTIMIZER_MODEL", "google-gla:gemini-2.5-flash")
    get_settings.cache_clear()
    auditor.get_auditor_agent.cache_clear()
    try:
        with patch.object(auditor, "build_model", wraps=auditor.build_model) as spy:
            auditor.get_auditor_agent()
        spy.assert_called_once_with("anthropic:claude-sonnet-5-5", env_var="OPTIMIZATION_MODEL")
    finally:
        auditor.get_auditor_agent.cache_clear()
        get_settings.cache_clear()


# --- B: bounded tool loop in optimizer v2 ---

def _run_optimizer(job, source, htmls):
    """Run the v2 agent with a fake model that calls check_content_length once per html.

    Returns (tool_names_offered, tool_return_contents, render_calls).
    """
    from hr_breaker.agents import optimizer_v2

    renderer = MagicMock()
    renderer.render.return_value = SimpleNamespace(page_count=1, pdf_bytes=b"%PDF")
    offered: list[str] = []
    calls = iter(htmls)

    def model_fn(messages, info: AgentInfo):
        if not offered:
            offered.extend(t.name for t in info.function_tools)
        html = next(calls, None)
        if html is not None:
            return ModelResponse(parts=[ToolCallPart("check_content_length", {"html": html})])
        audit = dict(
            ats_compatibility="ATS-Ready", recruiter_scan="Strong", bullet_quality="Moderate",
            seniority_calibration="Aligned", keyword_coverage="Strong", structure="Strong",
            concern_management="NA", consistency="Strong", overall="Strong", top_fixes=["a", "b", "c"],
        )
        return ModelResponse(parts=[ToolCallPart(
            info.output_tools[0].name, {"html": "<p>x</p>", "changes": ["c"], "audit": audit}
        )])

    with patch.object(optimizer_v2, "get_renderer", return_value=renderer):
        agent = optimizer_v2.get_optimizer_v2_agent(job, source)
        with agent.override(model=FunctionModel(model_fn)):
            result = agent.run_sync("optimize")
    returns = [
        p.content
        for m in result.all_messages()
        for p in getattr(m, "parts", [])
        if isinstance(p, ToolReturnPart) and p.tool_name == "check_content_length"
    ]
    return offered, returns, renderer.render.call_count


def test_preview_resume_tool_is_removed(job, source):
    offered, _, _ = _run_optimizer(job, source, [])
    assert "preview_resume" not in offered
    assert "check_content_length" in offered


def test_length_checks_are_capped_at_three_renders(job, source):
    _, returns, renders = _run_optimizer(job, source, [f"<p>{i}</p>" for i in range(5)])
    assert renders == 3
    assert [isinstance(r, dict) and "error" in r for r in returns] == [False, False, False, True, True]
    assert "return your best version" in returns[3]["error"]


def test_identical_html_is_cached_and_does_not_use_the_budget(job, source):
    _, returns, renders = _run_optimizer(job, source, ["<p>same</p>"] * 5)
    assert renders == 1
    assert all("error" not in r for r in returns)


def test_budget_error_is_not_cached_as_a_result_for_new_html(job, source):
    # 3 distinct real checks, then 2 more distinct ones: still only 3 renders
    _, _, renders = _run_optimizer(job, source, [f"<p>{i}</p>" for i in range(6)])
    assert renders == 3
