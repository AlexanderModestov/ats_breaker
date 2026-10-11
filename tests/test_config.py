"""Tests for config settings."""
from unittest.mock import patch


def test_optimizer_version_defaults_to_v2():
    from hr_breaker.config import get_settings
    get_settings.cache_clear()
    with patch.dict("os.environ", {"OPTIMIZER_VERSION": ""}, clear=False):
        settings = get_settings()
        assert settings.optimizer_version == "v2"
    get_settings.cache_clear()


def test_optimizer_version_reads_from_env():
    from hr_breaker.config import get_settings
    get_settings.cache_clear()
    with patch.dict("os.environ", {"OPTIMIZER_VERSION": "v1"}):
        settings = get_settings()
        assert settings.optimizer_version == "v1"
    get_settings.cache_clear()


def test_max_iterations_defaults_to_3():
    from hr_breaker.config import get_settings
    get_settings.cache_clear()
    with patch.dict("os.environ", {"MAX_ITERATIONS": ""}, clear=False):
        settings = get_settings()
        assert settings.max_iterations == 3
    get_settings.cache_clear()


def test_max_iterations_reads_from_env():
    from hr_breaker.config import get_settings
    get_settings.cache_clear()
    with patch.dict("os.environ", {"MAX_ITERATIONS": "5"}):
        settings = get_settings()
        assert settings.max_iterations == 5
    get_settings.cache_clear()


def test_name_extractor_model_defaults_to_flash_lite():
    from hr_breaker.config import get_settings
    get_settings.cache_clear()
    with patch.dict("os.environ", {"NAME_EXTRACTOR_MODEL": ""}, clear=False):
        settings = get_settings()
        assert settings.name_extractor_model == "google-gla:gemini-2.5-flash-lite"
    get_settings.cache_clear()


def test_name_extractor_model_reads_from_env():
    from hr_breaker.config import get_settings
    get_settings.cache_clear()
    with patch.dict("os.environ", {"NAME_EXTRACTOR_MODEL": "anthropic:claude-haiku-5-5"}):
        settings = get_settings()
        assert settings.name_extractor_model == "anthropic:claude-haiku-5-5"
    get_settings.cache_clear()


def test_default_model_chains_are_provider_prefixed_gemini_only():
    from hr_breaker.config import get_settings
    get_settings.cache_clear()
    with patch.dict("os.environ", {"OPTIMIZATION_MODEL": "", "COACH_MODEL": "", "NAME_EXTRACTOR_MODEL": ""}):
        s = get_settings()
        for chain in (s.optimization_model, s.coach_model, s.name_extractor_model):
            assert chain.startswith("google-gla:")
            assert "," not in chain
    get_settings.cache_clear()


def test_vertex_settings_are_gone():
    from hr_breaker.config import Settings
    for field in ("gcp_project", "gcp_location", "gemini_thinking_budget"):
        assert field not in Settings.model_fields


def test_model_settings_carry_provider_timeout():
    from hr_breaker.config import get_model_settings, get_settings
    get_settings.cache_clear()
    with patch.dict("os.environ", {"MODEL_PROVIDER_TIMEOUT": "42"}):
        assert get_model_settings() == {"timeout": 42.0}
    get_settings.cache_clear()


def test_provider_timeout_default_is_150_and_anthropic_max_tokens_default():
    from hr_breaker.config import Settings

    assert Settings.model_fields["model_provider_timeout"].default == 150.0
    assert Settings.model_fields["anthropic_max_tokens"].default == 16384


def test_optimizer_model_falls_back_to_optimization_model():
    from hr_breaker.config import get_settings
    get_settings.cache_clear()
    with patch.dict("os.environ", {"OPTIMIZATION_MODEL": "anthropic:claude-sonnet-5-5", "OPTIMIZER_MODEL": ""}):
        settings = get_settings()
        assert settings.optimizer_model == "anthropic:claude-sonnet-5-5"
    get_settings.cache_clear()


def test_optimizer_model_reads_from_env():
    from hr_breaker.config import get_settings
    get_settings.cache_clear()
    with patch.dict("os.environ", {"OPTIMIZATION_MODEL": "anthropic:claude-sonnet-5-5", "OPTIMIZER_MODEL": "google-gla:gemini-2.5-flash"}):
        settings = get_settings()
        assert settings.optimizer_model == "google-gla:gemini-2.5-flash"
        assert settings.optimization_model == "anthropic:claude-sonnet-5-5"
    get_settings.cache_clear()


def test_optimizer_model_defaults_to_default_optimization_model():
    from hr_breaker.config import get_settings
    get_settings.cache_clear()
    with patch.dict("os.environ", {"OPTIMIZATION_MODEL": "", "OPTIMIZER_MODEL": ""}):
        assert get_settings().optimizer_model == get_settings().optimization_model
    get_settings.cache_clear()
