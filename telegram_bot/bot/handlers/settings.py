"""Settings handler — /settings to choose default CV."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.services.api_client import APIClient

router = Router()


@router.message(Command("settings"))
async def settings_cmd(
    message: Message,
    backend_user: dict | None,
    api_client: APIClient,
    **kwargs,
):
    if not backend_user:
        await message.answer("Sign in first with /start.")
        return

    cvs = await api_client.get_cvs(message.from_user.id)
    if not cvs:
        await message.answer("You have no resumes uploaded yet. Send a file to add one.")
        return

    default_cv_id = backend_user.get("default_cv_id")
    buttons = [
        [InlineKeyboardButton(
            text=f"{'✅ ' if cv['id'] == default_cv_id else ''}{cv['original_filename']}",
            callback_data=f"set_default_cv:{cv['id']}",
        )]
        for cv in cvs
    ]
    await message.answer(
        "Choose your default resume:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("set_default_cv:"))
async def set_default_cv(
    callback: CallbackQuery,
    api_client: APIClient,
    **kwargs,
):
    cv_id = callback.data.split(":", 1)[1]
    await api_client.set_default_cv(callback.from_user.id, cv_id)
    await callback.answer("Default resume updated ✅")
    await callback.message.delete()
