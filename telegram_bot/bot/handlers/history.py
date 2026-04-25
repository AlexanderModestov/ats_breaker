"""History handler — /history shows recent optimization runs."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.services.api_client import APIClient

router = Router()


@router.message(Command("history"))
async def history_cmd(
    message: Message,
    backend_user: dict | None,
    api_client: APIClient,
    **kwargs,
):
    if not backend_user:
        await message.answer("Sign in first with /start.")
        return

    runs = (await api_client.get_recent_runs(message.from_user.id))[:5]
    if not runs:
        await message.answer("No optimization runs yet. Send a job URL to get started.")
        return

    buttons = [
        [InlineKeyboardButton(
            text=f"📄 {r.get('job_company', '?')} — {r.get('job_title', '?')}",
            callback_data=f"dl_pdf:{r['id']}",
        )]
        for r in runs
    ]
    await message.answer(
        "Your recent resumes:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("dl_pdf:"))
async def download_pdf(
    callback: CallbackQuery,
    api_client: APIClient,
    **kwargs,
):
    run_id = callback.data.split(":", 1)[1]
    await callback.answer("Downloading...")
    try:
        pdf_bytes = await api_client.get_optimization_pdf(callback.from_user.id, run_id)
        await callback.message.answer_document(
            BufferedInputFile(pdf_bytes, filename=f"resume_{run_id[:8]}.pdf"),
        )
    except Exception:
        await callback.message.answer("❌ Couldn't fetch the PDF. Try again later.")
