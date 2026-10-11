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


def test_agents_use_build_model_not_vertex_strings():
    from pathlib import Path
    agents_dir = Path(__file__).parent.parent / "src" / "hr_breaker" / "agents"
    for path in agents_dir.glob("*.py"):
        text = path.read_text()
        assert "google-vertex" not in text, path.name
        if "Agent(" in text and path.name != "__init__.py":
            assert "build_model(" in text, f"{path.name} builds an Agent without build_model"


async def test_api_lifespan_fails_fast_on_bad_llm_config(monkeypatch):
    from hr_breaker.api.main import app, lifespan
    from hr_breaker.config import get_settings

    monkeypatch.setenv("OPTIMIZATION_MODEL", "gemini-2.5-flash")  # legacy, unprefixed
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="OPTIMIZATION_MODEL"):
            async with lifespan(app):
                pass
    finally:
        get_settings.cache_clear()


def test_cli_optimize_reports_bad_llm_config(monkeypatch, tmp_path):
    from click.testing import CliRunner
    from hr_breaker.cli import cli
    from hr_breaker.config import get_settings

    monkeypatch.setenv("COACH_MODEL", "google-vertex:gemini-2.5-pro")
    get_settings.cache_clear()
    resume = tmp_path / "r.md"
    resume.write_text("x")
    try:
        result = CliRunner().invoke(cli, ["optimize", str(resume), "some job text"])
    finally:
        get_settings.cache_clear()
    assert result.exit_code != 0
    assert "unsupported provider" in result.output


def test_no_vertex_or_gcp_references_in_source():
    from pathlib import Path
    root = Path(__file__).parent.parent
    banned = ("vertexai", "google-vertex", "GOOGLE_CLOUD_PROJECT",
              "GOOGLE_CLOUD_LOCATION", "GOOGLE_APPLICATION_CREDENTIALS")
    for path in (root / "src").rglob("*.py"):
        text = path.read_text()
        for word in banned:
            assert word not in text, f"{word} in {path}"
    for name in ("pyproject.toml", ".env.example"):
        text = (root / name).read_text()
        for word in banned + ("google-cloud-aiplatform",):
            assert word not in text, f"{word} in {name}"


# --- C1: raw httpx transport errors from the Google SDK must fall through ---

import contextlib
import socket


@pytest.fixture
def hung_server():
    """Local socket that accepts connections and never answers."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    conns = []
    import threading

    def accept():
        while True:
            try:
                conns.append(srv.accept()[0])
            except OSError:
                return

    threading.Thread(target=accept, daemon=True).start()
    yield srv.getsockname()[1]
    srv.close()
    for c in conns:
        with contextlib.suppress(OSError):
            c.close()


@pytest.fixture
def closed_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _google_model(port: int):
    from pydantic_ai.models.google import GoogleModel
    from pydantic_ai.providers.google import GoogleProvider

    return GoogleModel(
        "gemini-2.5-flash",
        provider=GoogleProvider(api_key="x", base_url=f"http://127.0.0.1:{port}"),
    )


async def test_hung_google_primary_falls_through_to_secondary(hung_server):
    model = llm._fallback([_google_model(hung_server), _answering("from-secondary")])
    result = await Agent(model, model_settings={"timeout": 1}).run("hi")
    assert result.output == "from-secondary"


async def test_unreachable_google_primary_falls_through_to_secondary(closed_port):
    model = llm._fallback([_google_model(closed_port), _answering("from-secondary")])
    result = await Agent(model, model_settings={"timeout": 1}).run("hi")
    assert result.output == "from-secondary"


# --- I1: Google key precedence ---

def test_validate_chain_accepts_google_api_key_fallback(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "g-key")
    validate_chain(["google-gla:gemini-2.5-flash"])


def test_validate_chain_google_missing_both_names_gemini_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        validate_chain(["google-gla:gemini-2.5-flash"])


def test_gemini_key_wins_over_google_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    model = build_model("google-gla:gemini-2.5-flash")
    assert model.client._api_client.api_key == "gemini-key"


def test_google_key_used_when_gemini_key_absent(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    model = build_model("google-gla:gemini-2.5-flash")
    assert model.client._api_client.api_key == "google-key"


# --- I2: SDK-internal retries disabled ---

def test_anthropic_and_openai_clients_have_no_sdk_retries():
    assert build_model("anthropic:claude-sonnet-5-5").client.max_retries == 0
    assert build_model("openai:gpt-5").client.max_retries == 0


# --- I3: Anthropic max_tokens only on anthropic models ---

def test_anthropic_model_carries_max_tokens_default():
    assert build_model("anthropic:claude-sonnet-5-5").settings["max_tokens"] == 16384


def test_anthropic_max_tokens_configurable(monkeypatch):
    from hr_breaker.config import get_settings

    monkeypatch.setenv("ANTHROPIC_MAX_TOKENS", "2048")
    get_settings.cache_clear()
    assert build_model("anthropic:claude-sonnet-5-5").settings["max_tokens"] == 2048


def test_other_providers_get_no_max_tokens():
    for entry in ("google-gla:gemini-2.5-flash", "openai:gpt-5"):
        settings = build_model(entry).settings or {}
        assert "max_tokens" not in settings


def test_get_model_settings_has_only_timeout():
    from hr_breaker.config import get_model_settings

    assert set(get_model_settings()) == {"timeout"}


# --- Anthropic structured output must not force tool_choice (claude-sonnet-5-5 returns 400) ---

import asyncio
import json

from pydantic import BaseModel


class _Person(BaseModel):
    name: str


_ANTHROPIC_REPLY = json.dumps({
    "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
    "content": [{"type": "text", "text": '{"name": "Ada"}'}],
    "stop_reason": "end_turn", "stop_sequence": None,
    "usage": {"input_tokens": 1, "output_tokens": 1},
}).encode()


async def _fake_anthropic(bodies: list[dict]):
    """Local server that records each request body and answers with a canned message."""
    async def handle(reader, writer):
        head = await reader.readuntil(b"\r\n\r\n")
        length = next(int(h.split(b":")[1]) for h in head.split(b"\r\n") if h.lower().startswith(b"content-length"))
        bodies.append(json.loads(await reader.readexactly(length)))
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n"
            b"Content-Length: " + str(len(_ANTHROPIC_REPLY)).encode() + b"\r\n\r\n" + _ANTHROPIC_REPLY
        )
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


def _forces_tool(body: dict) -> bool:
    return body.get("tool_choice", {}).get("type") in ("any", "tool")


async def test_anthropic_structured_output_does_not_force_tool_choice(monkeypatch):
    bodies: list[dict] = []
    server, port = await _fake_anthropic(bodies)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", f"http://127.0.0.1:{port}")
    try:
        result = await Agent(build_model("anthropic:claude-sonnet-5-5"), output_type=_Person).run("who?")
    finally:
        server.close()
        await server.wait_closed()
    assert result.output == _Person(name="Ada")
    assert not _forces_tool(bodies[0])


async def test_anthropic_structured_output_with_function_tools_does_not_force_tool_choice(monkeypatch):
    bodies: list[dict] = []
    server, port = await _fake_anthropic(bodies)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", f"http://127.0.0.1:{port}")
    agent = Agent(build_model("anthropic:claude-sonnet-5-5"), output_type=_Person)

    @agent.tool_plain
    def ping() -> str:
        return "pong"

    try:
        result = await agent.run("who?")
    finally:
        server.close()
        await server.wait_closed()
    assert result.output == _Person(name="Ada")
    assert bodies[0]["tools"], "function tool should still be sent"
    assert not _forces_tool(bodies[0])


def test_anthropic_profile_is_prompted_but_keeps_provider_profile():
    profile = build_model("anthropic:claude-sonnet-5-5").profile
    assert profile.default_structured_output_mode == "prompted"
    assert profile.thinking_tags == ("<thinking>", "</thinking>")  # provider's own profile kept


def test_other_providers_keep_default_structured_output_mode():
    for entry in ("openai:gpt-5", "google-gla:gemini-2.5-flash"):
        assert build_model(entry).profile.default_structured_output_mode != "prompted"
