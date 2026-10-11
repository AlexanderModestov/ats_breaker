"""Config-driven LLM model factory: `provider:model[,provider:model...]` chains."""

import os
from collections.abc import Sequence

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from pydantic_ai.models import Model, infer_model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.profiles import ModelProfile
from pydantic_ai.providers import Provider, infer_provider
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider

from hr_breaker.config import get_settings, logger
from hr_breaker.utils.retry import is_transient_error

# Direct providers only. Each reads its key from this env var (pydantic-ai default).
PROVIDER_KEY_ENV = {
    "google-gla": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def _provider_key(provider: str) -> str | None:
    """API key for a provider. GEMINI_API_KEY is documented and wins; GOOGLE_API_KEY
    is accepted as a fallback (pydantic-ai alone would read GOOGLE_API_KEY first)."""
    if provider == "google-gla":
        return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    return os.getenv(PROVIDER_KEY_ENV[provider])


def parse_chain(value: str, *, env_var: str = "model") -> list[str]:
    """Split a comma-separated chain into trimmed `provider:model` entries."""
    entries = [e.strip() for e in value.split(",") if e.strip()]
    if not entries:
        raise ValueError(f"{env_var} is empty; expected provider:model[,provider:model...]")
    for entry in entries:
        provider, _, name = entry.partition(":")
        if not provider or not name:
            raise ValueError(
                f"{env_var}: {entry!r} must be in provider:model format, "
                f"e.g. google-gla:gemini-2.5-flash or anthropic:claude-sonnet-5-5"
            )
    return entries


def validate_chain(chain: Sequence[str], *, env_var: str = "model") -> None:
    """Fail fast on unsupported providers and missing API keys."""
    for entry in chain:
        provider = entry.partition(":")[0]
        key_var = PROVIDER_KEY_ENV.get(provider)
        if key_var is None:
            raise ValueError(
                f"{env_var}: unsupported provider {provider!r} in {entry!r}; "
                f"supported: {', '.join(PROVIDER_KEY_ENV)}"
            )
        if not _provider_key(provider):
            raise ValueError(f"{env_var}: {key_var} is not set (needed for {entry!r})")


def _fallback_condition(exc: Exception) -> bool:
    transient = is_transient_error(exc)
    if transient:
        logger.warning(f"LLM provider failed ({type(exc).__name__}: {exc}); trying next in chain")
    return transient


def _fallback(models: Sequence[Model | str]) -> FallbackModel:
    return FallbackModel(*models, fallback_on=_fallback_condition)


def _provider_factory(name: str) -> Provider:
    """Build providers explicitly. Our own retry + fallback own all retrying, so the
    Anthropic/OpenAI SDK clients get max_retries=0 (their default of 2 would stretch
    a hung provider to ~3x the timeout and starve the fallback)."""
    if name == "google-gla":
        return GoogleProvider(api_key=_provider_key(name))
    if name == "anthropic":
        return AnthropicProvider(anthropic_client=AsyncAnthropic(api_key=_provider_key(name), max_retries=0))
    if name == "openai":
        return OpenAIProvider(openai_client=AsyncOpenAI(api_key=_provider_key(name), max_retries=0))
    return infer_provider(name)


def _build_one(entry: str) -> Model:
    provider, _, name = entry.partition(":")
    if provider == "anthropic":
        anthropic_provider = _provider_factory(provider)
        # pydantic-ai gets structured output from Anthropic by forcing a tool call
        # (tool_choice any/tool), which newer Claude models reject with a 400. Prompted
        # output (JSON schema in the instructions, parsed from text) works on every model.
        # A custom profile replaces the provider's, so extend it instead of overriding it.
        prompted = ModelProfile(default_structured_output_mode="prompted")
        # Model-level setting (merged with agent-level timeout); only Anthropic needs it.
        return AnthropicModel(
            name,
            provider=anthropic_provider,
            profile=lambda model_name: (
                anthropic_provider.model_profile(model_name) or ModelProfile()
            ).update(prompted),
            settings={"max_tokens": get_settings().anthropic_max_tokens},
        )
    return infer_model(entry, provider_factory=_provider_factory)


def build_model(value: str, *, env_var: str = "model") -> Model:
    """Build a pydantic-ai model from a chain string.

    One entry returns that provider's model; several return a FallbackModel that
    moves to the next entry only on transient errors (429 / 5xx / connection).
    """
    chain = parse_chain(value, env_var=env_var)
    validate_chain(chain, env_var=env_var)
    if len(chain) == 1:
        return _build_one(chain[0])
    return _fallback([_build_one(e) for e in chain])


def validate_llm_config() -> None:
    """Validate every configured role chain. Called at API / CLI startup."""
    settings = get_settings()
    for env_var, value in (
        ("OPTIMIZATION_MODEL", settings.optimization_model),
        ("COACH_MODEL", settings.coach_model),
        ("NAME_EXTRACTOR_MODEL", settings.name_extractor_model),
    ):
        validate_chain(parse_chain(value, env_var=env_var), env_var=env_var)
