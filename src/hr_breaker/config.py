import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


def setup_logging() -> logging.Logger:
    general_level = os.getenv("LOG_LEVEL_GENERAL", "WARNING").upper()
    project_level = os.getenv("LOG_LEVEL", "WARNING").upper()

    logging.basicConfig(
        level=getattr(logging, general_level, logging.WARNING),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    )

    project_logger = logging.getLogger("hr_breaker")
    project_logger.setLevel(getattr(logging, project_level, logging.WARNING))
    return project_logger


logger = setup_logging()


class Settings(BaseModel):
    """Application settings."""

    google_api_key: str = ""
    gemini_pro_model: str = "gemini-3-pro-preview"
    gemini_flash_model: str = "gemini-3-flash-preview"
    gemini_thinking_budget: int | None = 8192
    cache_dir: Path = Path(".cache/resumes")
    output_dir: Path = Path("output")
    max_iterations: int = 5
    pass_threshold: float = 0.7
    fast_mode: bool = True

    # Supabase settings
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = ""
    supabase_jwt_secret: str = ""
    api_cors_origins: list[str] = ["http://localhost:3000"]

    # Stripe settings
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id_subscription: str = ""
    stripe_price_id_addon: str = ""

    # Paywall settings
    unlimited_users: list[str] = []
    trial_request_limit: int = 3
    subscription_request_limit: int = 50
    addon_request_count: int = 10

    # Scraper settings
    scraper_httpx_timeout: float = 15.0
    scraper_wayback_timeout: float = 10.0
    scraper_playwright_timeout: int = 30000
    scraper_httpx_max_retries: int = 3
    scraper_wayback_max_age_days: int = 30
    scraper_min_text_length: int = 200

    # Filter thresholds
    filter_hallucination_threshold: float = 0.9
    filter_keyword_threshold: float = 0.25
    filter_llm_threshold: float = 0.7
    filter_vector_threshold: float = 0.4
    filter_ai_generated_threshold: float = 0.4

    # Resume length limits
    resume_max_chars: int = 4500
    resume_max_words: int = 520
    resume_page2_overflow_chars: int = 1000

    # Keyword matcher params
    keyword_tfidf_max_features: int = 200
    keyword_tfidf_cutoff: float = 0.1
    keyword_max_missing_display: int = 10

    # Model settings
    sentence_transformer_model: str = "all-MiniLM-L6-v2"

    # Agent limits
    agent_name_extractor_chars: int = 2000


def _parse_cors_origins(value: str) -> list[str]:
    """Parse CORS origins from comma-separated string."""
    if not value:
        return ["http://localhost:3000"]
    return [origin.strip() for origin in value.split(",") if origin.strip()]


def _parse_unlimited_users(value: str) -> list[str]:
    """Parse unlimited users from comma-separated string."""
    if not value:
        return []
    return [email.strip().lower() for email in value.split(",") if email.strip()]


@lru_cache
def get_settings() -> Settings:
    thinking_env = os.getenv("GEMINI_THINKING_BUDGET")
    thinking_budget: int | None = 8192
    if thinking_env is not None:
        thinking_budget = int(thinking_env) if thinking_env else None
    return Settings(
        google_api_key=os.getenv("GOOGLE_API_KEY", ""),
        gemini_pro_model=os.getenv("GEMINI_PRO_MODEL") or "gemini-3-pro-preview",
        gemini_flash_model=os.getenv("GEMINI_FLASH_MODEL") or "gemini-3-flash-preview",
        gemini_thinking_budget=thinking_budget,
        fast_mode=os.getenv("HR_BREAKER_FAST_MODE", "true").lower() in ("true", "1", "yes"),
        # Scraper settings
        scraper_httpx_timeout=float(os.getenv("SCRAPER_HTTPX_TIMEOUT", "15")),
        scraper_wayback_timeout=float(os.getenv("SCRAPER_WAYBACK_TIMEOUT", "10")),
        scraper_playwright_timeout=int(os.getenv("SCRAPER_PLAYWRIGHT_TIMEOUT", "30000")),
        scraper_httpx_max_retries=int(os.getenv("SCRAPER_HTTPX_MAX_RETRIES", "3")),
        scraper_wayback_max_age_days=int(os.getenv("SCRAPER_WAYBACK_MAX_AGE_DAYS", "30")),
        scraper_min_text_length=int(os.getenv("SCRAPER_MIN_TEXT_LENGTH", "200")),
        # Filter thresholds
        filter_hallucination_threshold=float(os.getenv("FILTER_HALLUCINATION_THRESHOLD", "0.9")),
        filter_keyword_threshold=float(os.getenv("FILTER_KEYWORD_THRESHOLD", "0.25")),
        filter_llm_threshold=float(os.getenv("FILTER_LLM_THRESHOLD", "0.7")),
        filter_vector_threshold=float(os.getenv("FILTER_VECTOR_THRESHOLD", "0.4")),
        filter_ai_generated_threshold=float(os.getenv("FILTER_AI_GENERATED_THRESHOLD", "0.4")),
        # Resume length limits
        resume_max_chars=int(os.getenv("RESUME_MAX_CHARS", "4500")),
        resume_max_words=int(os.getenv("RESUME_MAX_WORDS", "520")),
        resume_page2_overflow_chars=int(os.getenv("RESUME_PAGE2_OVERFLOW_CHARS", "1000")),
        # Keyword matcher params
        keyword_tfidf_max_features=int(os.getenv("KEYWORD_TFIDF_MAX_FEATURES", "200")),
        keyword_tfidf_cutoff=float(os.getenv("KEYWORD_TFIDF_CUTOFF", "0.1")),
        keyword_max_missing_display=int(os.getenv("KEYWORD_MAX_MISSING_DISPLAY", "10")),
        # Model settings
        sentence_transformer_model=os.getenv("SENTENCE_TRANSFORMER_MODEL", "all-MiniLM-L6-v2"),
        # Agent limits
        agent_name_extractor_chars=int(os.getenv("AGENT_NAME_EXTRACTOR_CHARS", "2000")),
        # Supabase settings
        supabase_url=os.getenv("SUPABASE_URL", ""),
        supabase_anon_key=os.getenv("SUPABASE_ANON_KEY", ""),
        supabase_service_key=os.getenv("SUPABASE_SERVICE_KEY", ""),
        supabase_jwt_secret=os.getenv("SUPABASE_JWT_SECRET", ""),
        api_cors_origins=_parse_cors_origins(os.getenv("API_CORS_ORIGINS", "")),
        # Stripe settings
        stripe_secret_key=os.getenv("STRIPE_SECRET_KEY", ""),
        stripe_webhook_secret=os.getenv("STRIPE_WEBHOOK_SECRET", ""),
        stripe_price_id_subscription=os.getenv("STRIPE_PRICE_ID_SUBSCRIPTION", ""),
        stripe_price_id_addon=os.getenv("STRIPE_PRICE_ID_ADDON", ""),
        # Paywall settings
        unlimited_users=_parse_unlimited_users(os.getenv("UNLIMITED_USERS", "")),
        trial_request_limit=int(os.getenv("TRIAL_REQUEST_LIMIT", "3")),
        subscription_request_limit=int(os.getenv("SUBSCRIPTION_REQUEST_LIMIT", "50")),
        addon_request_count=int(os.getenv("ADDON_REQUEST_COUNT", "10")),
    )


def get_model_settings() -> dict[str, Any] | None:
    """Get GoogleModelSettings with thinking config if budget is set."""
    settings = get_settings()
    if settings.gemini_thinking_budget is not None:
        return {
            "google_thinking_config": {
                "thinking_budget": settings.gemini_thinking_budget
            }
        }
    return None
