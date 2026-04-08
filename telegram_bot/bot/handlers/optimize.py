"""Optimization flow handler."""

import re

from aiogram import F, Router
from aiogram.types import (
    BufferedInputFile,
    Document,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from bot.config import get_bot_settings
from bot.services.api_client import APIClient
from bot.services.polling import poll_until_done

router = Router()

URL_RE = re.compile(r"https?://\S+")
MIN_JOB_TEXT_LEN = 100


def _looks_like_job(text: str) -> bool:
    return bool(URL_RE.search(text)) or len(text) >= MIN_JOB_TEXT_LEN


def _unlinked_keyboard(web_app_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🔑 Sign in",
                web_app=WebAppInfo(url=f"{web_app_url}/signin"),
            )]
        ]
    )


def _coach_keyboard(run_id: str, web_app_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🎓 Open Coach",
                web_app=WebAppInfo(url=f"{web_app_url}/coach?runId={run_id}"),
            )]
        ]
    )


@router.message(F.text.func(_looks_like_job))
async def handle_job_input(
    message: Message,
    backend_user: dict | None,
    api_client: APIClient,
    **kwargs,
):
    settings = get_bot_settings()

    if not backend_user:
        await message.answer(
            "Please sign in first to use HR-Breaker:",
            reply_markup=_unlinked_keyboard(settings.web_app_url),
        )
        return

    telegram_id = message.from_user.id
    job_input = message.text

    # Get default CV
    cvs = await api_client.get_cvs(telegram_id)
    if not cvs:
        await message.answer(
            "📎 You don't have a resume on file yet.\n"
            "Please send your resume as a file (PDF, DOCX, or TXT)."
        )
        return

    cv_id = cvs[0]["id"]  # default to first (most recent)
    for cv in cvs:
        if cv.get("is_default"):
            cv_id = cv["id"]
            break

    status_msg = await message.answer("⏳ Optimizing your resume...")

    try:
        run = await api_client.start_optimization(telegram_id, cv_id, job_input)
        run_id = run["run_id"]

        result = await poll_until_done(api_client, telegram_id, run_id)

        pdf_bytes = await api_client.get_optimization_pdf(telegram_id, run_id)

        company = result.get("job_company", "company")
        title = result.get("job_title", "role")
        filename = f"{company}_{title}.pdf".replace(" ", "_")

        await status_msg.delete()
        await message.answer_document(
            BufferedInputFile(pdf_bytes, filename=filename),
            caption=f"✅ Resume optimized for <b>{title}</b> at <b>{company}</b>",
            reply_markup=_coach_keyboard(run_id, settings.web_app_url),
        )
    except TimeoutError:
        await status_msg.edit_text(
            "⏱ This is taking longer than usual. "
            "Use /history to download when ready."
        )
    except Exception:
        await status_msg.edit_text(
            "❌ Couldn't optimize your resume for this job.\n"
            "Try pasting the job description as text if you sent a URL."
        )


@router.message(F.document)
async def handle_document(
    message: Message,
    backend_user: dict | None,
    api_client: APIClient,
    **kwargs,
):
    settings = get_bot_settings()

    if not backend_user:
        await message.answer(
            "Please sign in first:",
            reply_markup=_unlinked_keyboard(settings.web_app_url),
        )
        return

    doc: Document = message.document
    allowed = {"application/pdf", "text/plain",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}

    if doc.mime_type not in allowed:
        await message.answer(
            "❌ Unsupported file type. Please send PDF, DOCX, or TXT (max 10 MB)."
        )
        return

    if doc.file_size > 10 * 1024 * 1024:
        await message.answer("❌ File is too large. Maximum size is 10 MB.")
        return

    file = await message.bot.get_file(doc.file_id)
    file_bytes = await message.bot.download_file(file.file_path)

    await api_client.upload_cv(
        message.from_user.id, doc.file_name or "resume.pdf", file_bytes.read()
    )
    await message.answer(
        "✅ Resume saved! Now send me a job URL or job description to optimize it."
    )
