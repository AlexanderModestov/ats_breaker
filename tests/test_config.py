"""Tests for config settings."""
from unittest.mock import patch


def test_optimizer_version_defaults_to_v1():
    from hr_breaker.config import get_settings
    get_settings.cache_clear()
    with patch.dict("os.environ", {"OPTIMIZER_VERSION": ""}, clear=False):
        settings = get_settings()
        assert settings.optimizer_version == "v1"
    get_settings.cache_clear()


def test_optimizer_version_reads_from_env():
    from hr_breaker.config import get_settings
    get_settings.cache_clear()
    with patch.dict("os.environ", {"OPTIMIZER_VERSION": "v2"}):
        settings = get_settings()
        assert settings.optimizer_version == "v2"
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
