"""Start handler — entry point and auth flow."""

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from bot.config import get_bot_settings
from bot.services.api_client import APIClient

router = Router()


@router.message(CommandStart())
async def start(
    message: Message,
    backend_user: dict | None,
    api_client: APIClient,
    **kwargs,
):
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
    await api_client.register_signin_message(
        telegram_id=message.from_user.id,
        chat_id=sent.chat.id,
        message_id=sent.message_id,
    )


@router.message(Command("help"))
async def help_cmd(message: Message, **kwargs):
    await message.answer(
        "<b>HR-Breaker</b>\n\n"
        "📎 <b>Send a job URL or description</b> — I'll optimize your default resume\n"
        "📄 <b>Send a resume file</b> (PDF/DOCX/TXT) — saved as your CV\n\n"
        "<b>Commands</b>\n"
        "/start — sign in / welcome\n"
        "/settings — choose default resume\n"
        "/history — last 5 optimizations\n"
        "/coach — open the interview coach\n"
        "/help — this message"
    )
