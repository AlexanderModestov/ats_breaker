"""Coach handler — /coach opens the interview coach Mini App."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from bot.config import get_bot_settings

router = Router()


@router.message(Command("coach"))
async def coach_cmd(message: Message, backend_user: dict | None, **kwargs):
    if not backend_user:
        await message.answer("Sign in first with /start.")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎓 Open Coach",
                    web_app=WebAppInfo(url=f"{get_bot_settings().web_app_url}/coach"),
                )
            ]
        ]
    )
    await message.answer(
        "🎓 Open the coach to prepare for an interview. "
        "Pick a position from the dropdown inside the app:",
        reply_markup=keyboard,
    )
