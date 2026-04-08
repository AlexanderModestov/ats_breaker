"""Bot configuration."""

import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


class BotSettings(BaseSettings):
    bot_token: str = ""
    bot_api_key: str = ""
    api_url: str = "http://localhost:8000"
    web_app_url: str = "https://app.hrbreaker.com"
    webhook_url: str = ""
    webhook_secret: str = ""

    model_config = {"env_prefix": ""}

    @classmethod
    def from_env(cls) -> "BotSettings":
        return cls(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            bot_api_key=os.getenv("BOT_API_KEY", ""),
            api_url=os.getenv("API_URL", "http://localhost:8000"),
            web_app_url=os.getenv("WEB_APP_URL", "https://app.hrbreaker.com"),
            webhook_url=os.getenv("WEBHOOK_URL", ""),
            webhook_secret=os.getenv("WEBHOOK_SECRET", ""),
        )


_settings: BotSettings | None = None


def get_bot_settings() -> BotSettings:
    global _settings
    if _settings is None:
        _settings = BotSettings.from_env()
    return _settings
