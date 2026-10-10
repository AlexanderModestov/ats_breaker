"""Config-driven LLM model factory: `provider:model[,provider:model...]` chains."""

import os
from collections.abc import Sequence

from pydantic_ai.models import Model, infer_model
from pydantic_ai.models.fallback import FallbackModel

from hr_breaker.config import get_settings, logger
from hr_breaker.utils.retry import is_transient_error

# Direct providers only. Each reads its key from this env var (pydantic-ai default).
PROVIDER_KEY_ENV = {
    "google-gla": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


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
        if not os.getenv(key_var):
            raise ValueError(f"{env_var}: {key_var} is not set (needed for {entry!r})")


def _fallback_condition(exc: Exception) -> bool:
    transient = is_transient_error(exc)
    if transient:
        logger.warning(f"LLM provider failed ({type(exc).__name__}: {exc}); trying next in chain")
    return transient


def _fallback(models: Sequence[Model | str]) -> FallbackModel:
    return FallbackModel(*models, fallback_on=_fallback_condition)


def build_model(value: str, *, env_var: str = "model") -> Model:
    """Build a pydantic-ai model from a chain string.

    One entry returns that provider's model; several return a FallbackModel that
    moves to the next entry only on transient errors (429 / 5xx / connection).
    """
    chain = parse_chain(value, env_var=env_var)
    validate_chain(chain, env_var=env_var)
    if len(chain) == 1:
        return infer_model(chain[0])
    return _fallback(chain)


def validate_llm_config() -> None:
    """Validate every configured role chain. Called at API / CLI startup."""
    settings = get_settings()
    for env_var, value in (
        ("OPTIMIZATION_MODEL", settings.optimization_model),
        ("COACH_MODEL", settings.coach_model),
        ("NAME_EXTRACTOR_MODEL", settings.name_extractor_model),
    ):
        validate_chain(parse_chain(value, env_var=env_var), env_var=env_var)
