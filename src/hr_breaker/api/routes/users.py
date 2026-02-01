"""User-related API routes."""

from fastapi import APIRouter, HTTPException

from hr_breaker.api.deps import CurrentUserWithEmail, SupabaseServiceDep
from hr_breaker.api.schemas import (
    AuthVerifyRequest,
    AuthVerifyResponse,
    UserProfile,
    UserProfileUpdate,
)
from hr_breaker.api.auth import AuthError, get_user_id_from_token, get_email_from_token
from hr_breaker.services.supabase import SupabaseError

router = APIRouter()


@router.post("/auth/verify", response_model=AuthVerifyResponse)
async def verify_auth(request: AuthVerifyRequest) -> AuthVerifyResponse:
    """Verify an authentication token."""
    try:
        user_id = get_user_id_from_token(request.access_token)
        email = get_email_from_token(request.access_token)
        return AuthVerifyResponse(valid=True, user_id=user_id, email=email)
    except AuthError:
        return AuthVerifyResponse(valid=False)


@router.get("/me", response_model=UserProfile)
async def get_current_profile(
    user: CurrentUserWithEmail,
    supabase: SupabaseServiceDep,
) -> UserProfile:
    """Get the current user's profile."""
    user_id, email = user

    profile = supabase.get_profile(user_id)

    if not profile:
        # Create profile if it doesn't exist
        try:
            profile = supabase.create_profile(user_id, email or "")
        except SupabaseError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    return UserProfile(
        id=profile["id"],
        email=profile["email"],
        name=profile.get("name"),
        theme=profile.get("theme", "minimal"),
        created_at=profile["created_at"],
    )


@router.patch("/me", response_model=UserProfile)
async def update_current_profile(
    updates: UserProfileUpdate,
    user: CurrentUserWithEmail,
    supabase: SupabaseServiceDep,
) -> UserProfile:
    """Update the current user's profile."""
    user_id, _ = user

    # Build update data, excluding None values
    update_data = {}
    if updates.name is not None:
        update_data["name"] = updates.name
    if updates.theme is not None:
        if updates.theme not in ("minimal", "professional", "bold"):
            raise HTTPException(
                status_code=400,
                detail="Theme must be one of: minimal, professional, bold",
            )
        update_data["theme"] = updates.theme

    if not update_data:
        raise HTTPException(status_code=400, detail="No updates provided")

    try:
        profile = supabase.update_profile(user_id, update_data)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        return UserProfile(
            id=profile["id"],
            email=profile["email"],
            name=profile.get("name"),
            theme=profile.get("theme", "minimal"),
            created_at=profile["created_at"],
        )
    except SupabaseError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
