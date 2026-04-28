"""Optimization flow handler."""

import asyncio
import logging
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
from bot.services.api_client import (
    APIClient,
    BackendError,
    JobUnavailableError,
    QuotaExceededError,
)
from bot.services.filename import format_resume_filename
from bot.services.polling import poll_until_done

logger = logging.getLogger(__name__)

router = Router()

URL_RE = re.compile(r"https?://\S+")
MIN_JOB_TEXT_LEN = 100
BACKGROUND_POLL_TIMEOUT = 900

_background_tasks: set[asyncio.Task] = set()


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


async def _continue_polling_in_background(
    message: Message,
    status_msg: Message,
    api_client: APIClient,
    telegram_id: int,
    run_id: str,
) -> None:
    """Keep polling after the foreground timeout and notify the user when done."""
    try:
        result = await poll_until_done(
            api_client, telegram_id, run_id, timeout=BACKGROUND_POLL_TIMEOUT
        )
        pdf_bytes = await api_client.get_optimization_pdf(telegram_id, run_id)

        job_parsed = result.get("job_parsed") or {}
        company = job_parsed.get("company") or "company"
        title = job_parsed.get("title") or "role"
        filename = format_resume_filename(result)

        await status_msg.edit_text(
            f"✅ Resume optimized for <b>{title}</b> at <b>{company}</b>"
        )
        await message.answer_document(
            BufferedInputFile(pdf_bytes, filename=filename),
        )
    except TimeoutError:
        await status_msg.edit_text(
            "⏱ Still working. Use /history to download once it's ready."
        )
    except Exception:
        logger.exception(
            "Background polling failed for telegram_id=%s run_id=%s",
            telegram_id,
            run_id,
        )
        await status_msg.edit_text(
            "❌ Something went wrong. Use /history to check the result."
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
        sent = await message.answer(
            "Please sign in first to use HR-Breaker:",
            reply_markup=_unlinked_keyboard(settings.web_app_url),
        )
        await api_client.register_signin_message(
            telegram_id=message.from_user.id,
            chat_id=sent.chat.id,
            message_id=sent.message_id,
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

    default_cv_id = backend_user.get("default_cv_id")
    cv_id = next(
        (cv["id"] for cv in cvs if cv["id"] == default_cv_id),
        cvs[0]["id"],
    )

    status_msg = await message.answer("⏳ Optimizing your resume...")

    try:
        run = await api_client.start_optimization(telegram_id, cv_id, job_input)
        run_id = run["run_id"]

        result = await poll_until_done(api_client, telegram_id, run_id)

        pdf_bytes = await api_client.get_optimization_pdf(telegram_id, run_id)

        # OptimizationStatus.job_parsed nests title/company — they're NOT top-level
        job_parsed = result.get("job_parsed") or {}
        company = job_parsed.get("company") or "company"
        title = job_parsed.get("title") or "role"
        filename = format_resume_filename(result)

        await status_msg.delete()
        await message.answer_document(
            BufferedInputFile(pdf_bytes, filename=filename),
            caption=f"✅ Resume optimized for <b>{title}</b> at <b>{company}</b>",
            reply_markup=_coach_keyboard(run_id, settings.web_app_url),
        )
    except QuotaExceededError:
        await status_msg.edit_text(
            f"💳 You're out of optimization credits.\n\n"
            f"Top up at {settings.web_app_url}/pricing"
        )
    except JobUnavailableError:
        await status_msg.edit_text(
            "❌ Couldn't read the job posting.\n"
            "Try pasting the job description as text instead of a URL."
        )
    except TimeoutError:
        await status_msg.edit_text(
            "⏱ Still optimizing — I'll update this message when it's ready."
        )
        task = asyncio.create_task(
            _continue_polling_in_background(
                message=message,
                status_msg=status_msg,
                api_client=api_client,
                telegram_id=telegram_id,
                run_id=run_id,
            )
        )
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
    except (BackendError, Exception):
        logger.exception("Optimization failed for telegram_id=%s", telegram_id)
        await status_msg.edit_text(
            "❌ Something went wrong on our side. Please try again in a minute."
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
        sent = await message.answer(
            "Please sign in first:",
            reply_markup=_unlinked_keyboard(settings.web_app_url),
        )
        await api_client.register_signin_message(
            telegram_id=message.from_user.id,
            chat_id=sent.chat.id,
            message_id=sent.message_id,
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

    try:
        await api_client.upload_cv(
            message.from_user.id, doc.file_name or "resume.pdf", file_bytes.read()
        )
        await message.answer(
            "✅ Resume saved! Now send me a job URL or job description to optimize it."
        )
    except BackendError:
        logger.exception("CV upload failed")
        await message.answer("❌ Couldn't save your resume. Please try again.")


@router.message(F.text & ~F.text.startswith("/"))
async def fallback_text(message: Message, **kwargs):
    await message.answer(
        "Send me a <b>job URL</b> or paste the full job description "
        "(at least 100 characters).\n\nNeed help? /help"
    )
