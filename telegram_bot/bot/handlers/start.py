"""Start handler — entry point and auth flow."""

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from bot.config import get_bot_settings
from bot.services import signin_tracker

router = Router()


@router.message(CommandStart())
async def start(message: Message, backend_user: dict | None, **kwargs):
    settings = get_bot_settings()

    if backend_user:
        await message.answer(
            f"👋 Welcome back! Send me a job URL or paste a job description "
            f"and I'll optimize your resume.\n\n"
            f"Use /help to see all commands."
        )
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔑 Sign in / Register",
                    web_app=WebAppInfo(url=f"{settings.web_app_url}/signin"),
                )
            ]
        ]
    )
    sent = await message.answer(
        "👋 Welcome to HR-Breaker!\n\n"
        "To get started, sign in with your Google account:",
        reply_markup=keyboard,
    )
    signin_tracker.remember(message.from_user.id, sent.chat.id, sent.message_id)
