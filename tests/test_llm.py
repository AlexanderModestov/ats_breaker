"""Tests for the config-driven LLM model factory."""
import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import FallbackExceptionGroup, ModelHTTPError
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.function import AgentInfo, FunctionModel

from hr_breaker import llm
from hr_breaker.llm import build_model, parse_chain, validate_chain, validate_llm_config


def test_parse_chain_single():
    assert parse_chain("google-gla:gemini-2.5-flash") == ["google-gla:gemini-2.5-flash"]


def test_parse_chain_trims_whitespace_and_ignores_empty_entries():
    assert parse_chain(" google-gla:a , anthropic:b ,") == ["google-gla:a", "anthropic:b"]


def test_parse_chain_empty_is_error():
    with pytest.raises(ValueError, match="OPTIMIZATION_MODEL"):
        parse_chain("  , ", env_var="OPTIMIZATION_MODEL")


def test_parse_chain_unprefixed_legacy_value_gives_clear_error():
    with pytest.raises(ValueError) as e:
        parse_chain("gemini-2.5-flash", env_var="OPTIMIZATION_MODEL")
    msg = str(e.value)
    assert "OPTIMIZATION_MODEL" in msg
    assert "provider:model" in msg
    assert "gemini-2.5-flash" in msg


def test_validate_chain_rejects_vertex_and_unknown_providers():
    for bad in ("google-vertex:gemini-2.5-flash", "mistral:large"):
        with pytest.raises(ValueError, match="unsupported provider"):
            validate_chain([bad], env_var="COACH_MODEL")


def test_validate_chain_missing_key_names_env_var(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError) as e:
        validate_chain(["google-gla:gemini-2.5-flash", "anthropic:claude-sonnet-5-5"],
                       env_var="OPTIMIZATION_MODEL")
    assert "ANTHROPIC_API_KEY" in str(e.value)
    assert "OPTIMIZATION_MODEL" in str(e.value)


def test_validate_chain_ok_when_keys_present():
    validate_chain(["google-gla:gemini-2.5-flash", "anthropic:claude-sonnet-5-5"])


def test_build_model_single_entry_is_not_fallback():
    model = build_model("anthropic:claude-sonnet-5-5")
    assert not isinstance(model, FallbackModel)
    assert model.system == "anthropic"


def test_build_model_multiple_entries_is_fallback_in_order():
    model = build_model("google-gla:gemini-2.5-flash,anthropic:claude-sonnet-5-5")
    assert isinstance(model, FallbackModel)
    assert [m.system for m in model.models] == ["google-gla", "anthropic"]


def _failing(status: int) -> FunctionModel:
    def fail(messages, info: AgentInfo):
        raise ModelHTTPError(status_code=status, model_name="primary", body=None)
    return FunctionModel(fail, model_name="primary")


def _answering(text: str) -> FunctionModel:
    def ok(messages, info: AgentInfo):
        return ModelResponse(parts=[TextPart(text)])
    return FunctionModel(ok, model_name="secondary")


async def test_fallback_on_transient_error_uses_secondary():
    model = llm._fallback([_failing(429), _answering("from-secondary")])
    result = await Agent(model).run("hi")
    assert result.output == "from-secondary"


async def test_no_fallback_on_auth_error():
    model = llm._fallback([_failing(401), _answering("from-secondary")])
    with pytest.raises(ModelHTTPError) as e:
        await Agent(model).run("hi")
    assert e.value.status_code == 401


async def test_all_models_transient_failure_raises_fallback_group():
    model = llm._fallback([_failing(503), _failing(429)])
    with pytest.raises(FallbackExceptionGroup):
        await Agent(model).run("hi")


def test_validate_llm_config_checks_all_three_roles(monkeypatch):
    from hr_breaker.config import get_settings
    monkeypatch.setenv("OPTIMIZATION_MODEL", "google-gla:gemini-2.5-flash")
    monkeypatch.setenv("NAME_EXTRACTOR_MODEL", "google-gla:gemini-2.5-flash-lite")
    monkeypatch.setenv("COACH_MODEL", "anthropic:claude-sonnet-5-5")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="COACH_MODEL"):
            validate_llm_config()
    finally:
        get_settings.cache_clear()
