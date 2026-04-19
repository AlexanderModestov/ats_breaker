"""Telegram bot authentication routes."""

import hashlib
import hmac
import json
import time
from typing import Annotated
from urllib.parse import parse_qsl, unquote

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from hr_breaker.api.deps import CurrentUser, SupabaseServiceDep
from hr_breaker.config import get_settings, logger

router = APIRouter()

WELCOME_AFTER_LINK_TEXT = (
    "✅ You're signed in!\n\n"
    "Send me a job URL or paste a job description and I'll optimize your resume.\n\n"
    "Use /help to see all commands."
)


def _validate_init_data(init_data: str) -> dict:
    """
    Validate Telegram Mini App initData signature.
    Returns parsed user dict if valid, raises HTTPException if invalid.
    """
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=500, detail="Bot token not configured")

    params = dict(parse_qsl(unquote(init_data), keep_blank_values=True))
    received_hash = params.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="Missing hash in initData")

    # Check auth_date not too old (10 minutes)
    auth_date = int(params.get("auth_date", 0))
    if time.time() - auth_date > 600:
        raise HTTPException(status_code=401, detail="initData expired")

    # Build data-check-string
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))

    # Compute secret key: HMAC-SHA256("WebAppData", bot_token)
    secret_key = hmac.new(
        b"WebAppData", settings.telegram_bot_token.encode(), hashlib.sha256
    ).digest()

    # Compute expected hash
    expected_hash = hmac.new(
        secret_key, data_check.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise HTTPException(status_code=401, detail="Invalid initData signature")

    user_json = params.get("user", "{}")
    return json.loads(user_json)


class LinkTelegramRequest(BaseModel):
    telegram_id: int


class TelegramSessionRequest(BaseModel):
    init_data: str


class PendingSigninRequest(BaseModel):
    telegram_id: int
    chat_id: int
    message_id: int


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


@router.get("/me")
async def get_me_by_telegram(
    supabase: SupabaseServiceDep,
    x_telegram_user_id: Annotated[str | None, Header()] = None,
    x_bot_api_key: Annotated[str | None, Header()] = None,
):
    """Get user profile by Telegram ID (bot use only)."""
    settings = get_settings()
    if not x_bot_api_key or x_bot_api_key != settings.bot_api_key:
        raise HTTPException(status_code=401, detail="Invalid bot API key")
    if not x_telegram_user_id:
        raise HTTPException(status_code=400, detail="Missing X-Telegram-User-Id")

    profile = supabase.get_profile_by_telegram_id(int(x_telegram_user_id))
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    return profile
