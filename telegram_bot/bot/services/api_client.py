"""HTTP client for FastAPI backend."""

import logging

import httpx
from bot.config import get_bot_settings

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Base class for backend API errors."""


class QuotaExceededError(APIError):
    """User has run out of optimization quota (HTTP 402)."""


class JobUnavailableError(APIError):
    """Job posting could not be retrieved or parsed (HTTP 422)."""


class BackendError(APIError):
    """Generic backend or network failure (5xx, network errors)."""


class APIClient:
    def __init__(self):
        settings = get_bot_settings()
        self._base_url = settings.api_url
        self._headers = {
            "X-Bot-Api-Key": settings.bot_api_key,
        }

    def _user_headers(self, telegram_id: int) -> dict:
        return {**self._headers, "X-Telegram-User-Id": str(telegram_id)}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        telegram_id: int,
        timeout: float | None = None,
        **kwargs,
    ) -> httpx.Response:
        """Make a user-authenticated request, mapping failures to BackendError.

        ``timeout=None`` keeps httpx's default; pass a number to override.
        """
        client_kwargs = {} if timeout is None else {"timeout": timeout}
        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                r = await client.request(
                    method,
                    f"{self._base_url}{path}",
                    headers=self._user_headers(telegram_id),
                    **kwargs,
                )
                r.raise_for_status()
                return r
        except httpx.HTTPStatusError as e:
            raise BackendError(f"{e.response.status_code}: {e.response.text}") from e
        except httpx.RequestError as e:
            raise BackendError(f"Network error: {e}") from e

    async def get_user(self, telegram_id: int) -> dict | None:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"{self._base_url}/api/me",
                    headers=self._user_headers(telegram_id),
                )
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                return r.json()
        except httpx.HTTPStatusError as e:
            raise BackendError(f"{e.response.status_code}: {e.response.text}") from e
        except httpx.RequestError as e:
            raise BackendError(f"Network error: {e}") from e

    async def register_signin_message(
        self, telegram_id: int, chat_id: int, message_id: int
    ) -> None:
        """Tell backend which "Sign in" message to edit after linking."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                r = await client.post(
                    f"{self._base_url}/api/auth/telegram/pending-signin",
                    headers=self._headers,
                    json={
                        "telegram_id": telegram_id,
                        "chat_id": chat_id,
                        "message_id": message_id,
                    },
                )
                r.raise_for_status()
            except Exception as e:
                # Non-fatal: cleanup is best-effort.
                logger.warning(
                    "Failed to register sign-in message for telegram_id=%s: %s",
                    telegram_id,
                    e,
                )

    async def get_cvs(self, telegram_id: int) -> list[dict]:
        r = await self._request("GET", "/api/cvs", telegram_id=telegram_id)
        return r.json().get("cvs", [])

    async def upload_cv(self, telegram_id: int, filename: str, content: bytes) -> dict:
        r = await self._request(
            "POST",
            "/api/cvs",
            telegram_id=telegram_id,
            files={"file": (filename, content)},
        )
        return r.json()

    async def start_optimization(
        self, telegram_id: int, cv_id: str, job_input: str
    ) -> dict:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{self._base_url}/api/optimize",
                    headers=self._user_headers(telegram_id),
                    json={"cv_id": cv_id, "job_input": job_input},
                    timeout=30,
                )
                r.raise_for_status()
                return r.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 402:
                raise QuotaExceededError(e.response.text) from e
            if e.response.status_code in (422, 502):
                raise JobUnavailableError(e.response.text) from e
            raise BackendError(f"{e.response.status_code}: {e.response.text}") from e
        except httpx.RequestError as e:
            raise BackendError(f"Network error: {e}") from e

    async def get_optimization_status(
        self, telegram_id: int, run_id: str
    ) -> dict:
        r = await self._request(
            "GET", f"/api/optimize/{run_id}", telegram_id=telegram_id, timeout=10
        )
        return r.json()

    async def get_optimization_pdf(
        self, telegram_id: int, run_id: str
    ) -> bytes:
        r = await self._request(
            "GET", f"/api/optimize/{run_id}/pdf", telegram_id=telegram_id, timeout=30
        )
        return r.content

    async def get_recent_runs(self, telegram_id: int) -> list[dict]:
        r = await self._request(
            "GET", "/api/optimize?limit=5", telegram_id=telegram_id
        )
        return r.json().get("runs", [])

    async def set_default_cv(self, telegram_id: int, cv_id: str) -> None:
        await self._request(
            "PATCH", "/api/me", telegram_id=telegram_id, json={"default_cv_id": cv_id}
        )
