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


def _effective_default_id(cvs: list[dict], default_cv_id: str | None) -> str:
    """Mirror the /optimize fallback: stored default if it still exists, else first CV."""
    if default_cv_id and any(cv["id"] == default_cv_id for cv in cvs):
        return default_cv_id
    return cvs[0]["id"]


def _build_cv_keyboard(cvs: list[dict], effective_default_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"{'✅ ' if cv['id'] == effective_default_id else ''}{cv['original_filename']}",
                callback_data=f"set_default_cv:{cv['id']}",
            )]
            for cv in cvs
        ]
    )


def _settings_text(cvs: list[dict], effective_default_id: str) -> str:
    default_cv = next(cv for cv in cvs if cv["id"] == effective_default_id)
    return (
        f"<b>Default resume for optimization:</b>\n"
        f"📄 {default_cv['original_filename']}\n\n"
        f"Tap another resume below to change it."
    )


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

    effective_default_id = _effective_default_id(cvs, backend_user.get("default_cv_id"))
    await message.answer(
        _settings_text(cvs, effective_default_id),
        reply_markup=_build_cv_keyboard(cvs, effective_default_id),
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

    cvs = await api_client.get_cvs(callback.from_user.id)
    await callback.message.edit_text(
        _settings_text(cvs, cv_id),
        reply_markup=_build_cv_keyboard(cvs, cv_id),
    )
