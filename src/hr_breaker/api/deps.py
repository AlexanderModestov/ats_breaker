"""Dependency injection for FastAPI routes."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException

from hr_breaker.api.auth import AuthError, get_user_id_from_token, get_email_from_token
from hr_breaker.config import get_settings
from hr_breaker.services.access_control import check_feature_access
from hr_breaker.services.supabase import SupabaseService
from hr_breaker.services.tiers import Feature


def get_supabase_service() -> SupabaseService:
    """Get Supabase service instance."""
    return SupabaseService()


def get_profile_or_404(supabase: SupabaseService, user_id: str) -> dict:
    """Fetch the user's profile or raise 404."""
    profile = supabase.get_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


def get_run_or_404(supabase: SupabaseService, run_id: str, user_id: str) -> dict:
    """Fetch an optimization run owned by the user or raise 404."""
    run = supabase.get_optimization_run(run_id, user_id)
    if not run:
        raise HTTPException(status_code=404, detail="Optimization run not found")
    return run


def _resolve_bot_user(
    supabase: SupabaseService,
    x_bot_api_key: str | None,
    x_telegram_user_id: str | None,
) -> str | None:
    """
    If bot auth headers are present and valid, return the linked user's ID.
    Returns None when neither header is set (caller falls back to JWT auth).
    Raises HTTPException if headers are present but invalid.
    """
    if not x_bot_api_key and not x_telegram_user_id:
        return None

    settings = get_settings()
    if not settings.bot_api_key or x_bot_api_key != settings.bot_api_key:
        raise HTTPException(status_code=401, detail="Invalid bot API key")
    if not x_telegram_user_id:
        raise HTTPException(status_code=400, detail="Missing X-Telegram-User-Id")
    try:
        telegram_id = int(x_telegram_user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid X-Telegram-User-Id") from e

    profile = supabase.get_profile_by_telegram_id(telegram_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Telegram user not linked")
    return profile["id"]


async def get_current_user_email(
    supabase: Annotated[SupabaseService, Depends(get_supabase_service)],
    authorization: Annotated[str | None, Header()] = None,
    x_bot_api_key: Annotated[str | None, Header()] = None,
    x_telegram_user_id: Annotated[str | None, Header()] = None,
) -> tuple[str, str | None]:
    """
    Same two auth schemes as ``get_current_user``; also returns the user's
    email. For bot auth the email is read from the linked Supabase profile
    (may be ``None`` if the profile has no email on file).
    """
    bot_user_id = _resolve_bot_user(supabase, x_bot_api_key, x_telegram_user_id)
    if bot_user_id is not None:
        profile = supabase.get_profile(bot_user_id)
        email = profile.get("email") if profile else None
        return bot_user_id, email

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization header format")

    token = parts[1]

    try:
        user_id = get_user_id_from_token(token)
        email = get_email_from_token(token)
        return user_id, email
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


async def get_current_user(
    supabase: Annotated[SupabaseService, Depends(get_supabase_service)],
    authorization: Annotated[str | None, Header()] = None,
    x_bot_api_key: Annotated[str | None, Header()] = None,
    x_telegram_user_id: Annotated[str | None, Header()] = None,
) -> str:
    """
    Resolve the current user via one of two auth schemes:

    1. Web/Mini App: ``Authorization: Bearer <Supabase JWT>``
    2. Telegram bot: ``X-Bot-Api-Key`` + ``X-Telegram-User-Id`` — looked up
       in ``profiles.telegram_id``.
    """
    user_id, _ = await get_current_user_email(
        supabase, authorization, x_bot_api_key, x_telegram_user_id
    )
    return user_id


# Type aliases for dependency injection
CurrentUser = Annotated[str, Depends(get_current_user)]
CurrentUserWithEmail = Annotated[tuple[str, str | None], Depends(get_current_user_email)]
SupabaseServiceDep = Annotated[SupabaseService, Depends(get_supabase_service)]


def require_feature(feature: Feature):
    """FastAPI dependency factory: enforces tier requirement, raises 402 otherwise.

    Usage:
        @router.post("/sessions")
        async def x(user = Depends(require_feature(Feature.COACH))):
            ...
    """
    def _dep(
        user: CurrentUserWithEmail,
        supabase: SupabaseServiceDep,
    ) -> tuple[str, str | None]:
        user_id, user_email = user
        profile = get_profile_or_404(supabase, user_id)
        result = check_feature_access(feature, user_email or "", profile)
        if not result.allowed:
            raise HTTPException(402, detail=result.to_dict())
        return user
    return _dep
