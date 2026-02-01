"""Dependency injection for FastAPI routes."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException

from hr_breaker.api.auth import AuthError, get_user_id_from_token, get_email_from_token
from hr_breaker.services.supabase import SupabaseService


def get_supabase_service() -> SupabaseService:
    """Get Supabase service instance."""
    return SupabaseService()


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """
    Extract and verify the current user from the Authorization header.

    Args:
        authorization: The Authorization header value

    Returns:
        The user ID

    Raises:
        HTTPException: If authentication fails
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    # Extract token from "Bearer <token>" format
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization header format")

    token = parts[1]

    try:
        user_id = get_user_id_from_token(token)
        return user_id
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


async def get_current_user_email(
    authorization: Annotated[str | None, Header()] = None,
) -> tuple[str, str | None]:
    """
    Extract user ID and email from the Authorization header.

    Returns:
        Tuple of (user_id, email)
    """
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


# Type aliases for dependency injection
CurrentUser = Annotated[str, Depends(get_current_user)]
CurrentUserWithEmail = Annotated[tuple[str, str | None], Depends(get_current_user_email)]
SupabaseServiceDep = Annotated[SupabaseService, Depends(get_supabase_service)]
