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
from bot.services.filename import format_resume_filename

router = Router()

PAGE_SIZE = 5


def _history_keyboard(runs: list[dict], page: int) -> InlineKeyboardMarkup:
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_runs = runs[start:end]

    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=f"📄 {r.get('job_company', '?')} — {r.get('job_title', '?')}",
                callback_data=f"dl_pdf:{r['id']}",
            )
        ]
        for r in page_runs
    ]

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"hist:{page - 1}"))
    if end < len(runs):
        nav.append(InlineKeyboardButton(text="Далее ▶️", callback_data=f"hist:{page + 1}"))
    if nav:
        rows.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=rows)


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

    runs = await api_client.get_recent_runs(message.from_user.id)
    if not runs:
        await message.answer("No optimization runs yet. Send a job URL to get started.")
        return

    await message.answer(
        "Your recent resumes:",
        reply_markup=_history_keyboard(runs, 0),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("hist:"))
async def history_page(
    callback: CallbackQuery,
    api_client: APIClient,
    **kwargs,
):
    try:
        page = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer()
        return

    runs = await api_client.get_recent_runs(callback.from_user.id)
    await callback.message.edit_reply_markup(
        reply_markup=_history_keyboard(runs, page),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("dl_pdf:"))
async def download_pdf(
    callback: CallbackQuery,
    api_client: APIClient,
    **kwargs,
):
    run_id = callback.data.split(":", 1)[1]
    await callback.answer("Downloading...")
    try:
        run = await api_client.get_optimization_status(callback.from_user.id, run_id)
        pdf_bytes = await api_client.get_optimization_pdf(callback.from_user.id, run_id)
        await callback.message.answer_document(
            BufferedInputFile(pdf_bytes, filename=format_resume_filename(run)),
        )
    except Exception:
        await callback.message.answer("❌ Couldn't fetch the PDF. Try again later.")
