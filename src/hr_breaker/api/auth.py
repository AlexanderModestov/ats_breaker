"""JWT verification via Supabase."""

from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import httpx
from jose import JWTError, jwt, jwk
from jose.utils import base64url_decode

from hr_breaker.config import get_settings, logger


class AuthError(Exception):
    """Authentication error."""

    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@lru_cache(maxsize=1)
def _get_jwks(supabase_url: str) -> dict[str, Any]:
    """Fetch JWKS from Supabase (cached)."""
    jwks_url = f"{supabase_url}/auth/v1/.well-known/jwks.json"
    try:
        response = httpx.get(jwks_url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Failed to fetch JWKS: {e}")
        raise AuthError("Failed to fetch JWKS", status_code=500) from e


def _get_signing_key(token: str, jwks: dict[str, Any]) -> dict[str, Any]:
    """Get the signing key from JWKS that matches the token's kid."""
    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header.get("kid")

    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key

    # If no kid match, try the first key
    if jwks.get("keys"):
        return jwks["keys"][0]

    raise AuthError("No matching signing key found")


def verify_jwt(token: str) -> dict[str, Any]:
    """
    Verify a Supabase JWT token.

    Supports both HS256 (symmetric) and ES256 (asymmetric) algorithms.

    Args:
        token: The JWT token to verify

    Returns:
        The decoded token payload

    Raises:
        AuthError: If the token is invalid or expired
    """
    settings = get_settings()

    try:
        # Decode header to check algorithm
        unverified_header = jwt.get_unverified_header(token)
        token_alg = unverified_header.get("alg")

        if token_alg == "HS256":
            # Symmetric verification with JWT secret
            if not settings.supabase_jwt_secret:
                raise AuthError("JWT secret not configured", status_code=500)

            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
        elif token_alg == "ES256":
            # Asymmetric verification with JWKS
            if not settings.supabase_url:
                raise AuthError("Supabase URL not configured", status_code=500)

            jwks = _get_jwks(settings.supabase_url)
            signing_key = _get_signing_key(token, jwks)

            payload = jwt.decode(
                token,
                signing_key,
                algorithms=["ES256"],
                audience="authenticated",
            )
        else:
            raise AuthError(f"Unsupported JWT algorithm: {token_alg}")

        # Check expiration
        exp = payload.get("exp")
        if exp:
            exp_datetime = datetime.fromtimestamp(exp, tz=timezone.utc)
            if exp_datetime < datetime.now(tz=timezone.utc):
                raise AuthError("Token has expired")

        return payload

    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        raise AuthError("Invalid token") from e


def get_user_id_from_token(token: str) -> str:
    """
    Extract user ID from JWT token.

    Args:
        token: The JWT token

    Returns:
        The user ID (sub claim)

    Raises:
        AuthError: If the token is invalid or missing user ID
    """
    payload = verify_jwt(token)
    user_id = payload.get("sub")
    if not user_id:
        raise AuthError("Token missing user ID")
    return user_id


def get_email_from_token(token: str) -> str | None:
    """
    Extract email from JWT token.

    Args:
        token: The JWT token

    Returns:
        The user email or None
    """
    payload = verify_jwt(token)
    email = payload.get("email")
    logger.info(f"Extracted email from token: {email}")
    return email
