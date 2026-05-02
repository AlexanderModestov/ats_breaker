"""Telegram bot authentication routes."""

from typing import Annotated

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from hr_breaker.api.auth_telegram import (
    InitDataError,
    parse_and_validate_init_data,
)
from hr_breaker.api.deps import CurrentUser, SupabaseServiceDep
from hr_breaker.config import get_settings, logger

router = APIRouter()

WELCOME_AFTER_LINK_TEXT = (
    "✅ You're signed in!\n\n"
    "Send me a job URL or paste a job description and I'll optimize your resume.\n\n"
    "Use /help to see all commands."
)


class LinkTelegramRequest(BaseModel):
    telegram_id: int


class PendingSigninRequest(BaseModel):
    telegram_id: int
    chat_id: int
    message_id: int


class ExchangeRequest(BaseModel):
    init_data: str


INIT_DATA_MAX_AGE_SECONDS = 3600


async def _edit_welcome_message(chat_id: int, message_id: int) -> None:
    """Edit the bot's "Sign in" message into a welcome message without keyboard.

    Clears the inline keyboard by sending an empty ``inline_keyboard`` — Telegram
    preserves the existing markup if ``reply_markup`` is omitted, so we must
    pass it explicitly.
    """
    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.warning("Cannot edit signin message: telegram_bot_token not set")
        return

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": WELCOME_AFTER_LINK_TEXT,
        "reply_markup": {"inline_keyboard": []},
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                logger.warning(
                    f"Telegram editMessageText failed: {resp.status_code} {resp.text}"
                )
    except Exception as e:
        logger.warning(f"Telegram editMessageText error: {e}")


@router.post("/link")
async def link_telegram(
    body: LinkTelegramRequest,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
):
    """Link a Telegram ID to the currently authenticated user."""
    supabase.link_telegram(user_id, body.telegram_id)

    pending = supabase.pop_pending_signin_message(body.telegram_id)
    if pending:
        await _edit_welcome_message(
            chat_id=int(pending["chat_id"]),
            message_id=int(pending["message_id"]),
        )
    return {"ok": True}


@router.post("/pending-signin")
async def register_pending_signin(
    body: PendingSigninRequest,
    supabase: SupabaseServiceDep,
    x_bot_api_key: Annotated[str | None, Header()] = None,
):
    """Bot-only: register a sent "Sign in" message for later cleanup."""
    settings = get_settings()
    if not x_bot_api_key or x_bot_api_key != settings.bot_api_key:
        raise HTTPException(status_code=401, detail="Invalid bot API key")
    supabase.set_pending_signin_message(
        telegram_id=body.telegram_id,
        chat_id=body.chat_id,
        message_id=body.message_id,
    )
    return {"ok": True}


@router.post("/exchange")
async def exchange_init_data(
    body: ExchangeRequest,
    supabase: SupabaseServiceDep,
):
    """Exchange a signed Telegram WebApp initData payload for a Supabase
    magic-link token_hash. Used by the Mini App to silently re-authenticate
    a previously-linked user without re-running Google OAuth.
    """
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise HTTPException(500, "Server is missing telegram_bot_token")

    try:
        validated = parse_and_validate_init_data(
            body.init_data,
            settings.telegram_bot_token,
            max_age_seconds=INIT_DATA_MAX_AGE_SECONDS,
        )
    except InitDataError as e:
        raise HTTPException(401, str(e)) from e

    profile = supabase.get_profile_by_telegram_id(validated.telegram_id)
    if not profile:
        raise HTTPException(404, "Telegram user not linked")

    email = profile.get("email")
    if not email:
        raise HTTPException(409, "Profile has no email")

    token_hash = supabase.generate_magiclink(email)
    return {"token_hash": token_hash, "email": email}
