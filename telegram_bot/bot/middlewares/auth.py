"""Auth middleware: checks if telegram_id is linked to an account."""

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import TelegramObject, Message

from bot.services import signin_tracker
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
        if isinstance(event, Message) and event.from_user:
            user = await client.get_user(event.from_user.id)
            if user:
                await _clear_pending_signin(event, event.from_user.id)
        data["api_client"] = client
        data["backend_user"] = user
        return await handler(event, data)


async def _clear_pending_signin(event: Message, telegram_id: int) -> None:
    pending = signin_tracker.pop_all(telegram_id)
    if not pending:
        return
    for chat_id, message_id in pending:
        try:
            await event.bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=None,
            )
        except TelegramBadRequest:
            # Message was deleted or keyboard already cleared — ignore.
            pass
