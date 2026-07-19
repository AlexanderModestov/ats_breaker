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
        assert settings.name_extractor_model == "gemini-2.5-flash-lite"
    get_settings.cache_clear()


def test_name_extractor_model_reads_from_env():
    from hr_breaker.config import get_settings
    get_settings.cache_clear()
    with patch.dict("os.environ", {"NAME_EXTRACTOR_MODEL": "gemini-2.5-flash"}):
        settings = get_settings()
        assert settings.name_extractor_model == "gemini-2.5-flash"
    get_settings.cache_clear()
