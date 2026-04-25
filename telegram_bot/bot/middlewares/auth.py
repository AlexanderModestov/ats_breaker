"""Auth middleware: checks if telegram_id is linked to an account."""

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.services.api_client import APIClient


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        client = APIClient()
        user = None
        if isinstance(event, (Message, CallbackQuery)) and event.from_user:
            user = await client.get_user(event.from_user.id)
        data["api_client"] = client
        data["backend_user"] = user
        return await handler(event, data)
