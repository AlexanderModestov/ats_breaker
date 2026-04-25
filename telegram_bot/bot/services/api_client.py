"""HTTP client for FastAPI backend."""

import httpx
from bot.config import get_bot_settings


class APIClient:
    def __init__(self):
        settings = get_bot_settings()
        self._base_url = settings.api_url
        self._headers = {
            "X-Bot-Api-Key": settings.bot_api_key,
        }

    def _user_headers(self, telegram_id: int) -> dict:
        return {**self._headers, "X-Telegram-User-Id": str(telegram_id)}

    async def get_user(self, telegram_id: int) -> dict | None:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self._base_url}/api/auth/telegram/me",
                headers=self._user_headers(telegram_id),
            )
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()

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
            except Exception:
                # Non-fatal: cleanup is best-effort.
                pass

    async def get_cvs(self, telegram_id: int) -> list[dict]:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self._base_url}/api/cvs",
                headers=self._user_headers(telegram_id),
            )
            r.raise_for_status()
            return r.json().get("cvs", [])

    async def upload_cv(self, telegram_id: int, filename: str, content: bytes) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{self._base_url}/api/cvs",
                headers=self._user_headers(telegram_id),
                files={"file": (filename, content)},
            )
            r.raise_for_status()
            return r.json()

    async def start_optimization(
        self, telegram_id: int, cv_id: str, job_input: str
    ) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{self._base_url}/api/optimize",
                headers=self._user_headers(telegram_id),
                json={"cv_id": cv_id, "job_input": job_input},
                timeout=30,
            )
            r.raise_for_status()
            return r.json()

    async def get_optimization_status(
        self, telegram_id: int, run_id: str
    ) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self._base_url}/api/optimize/{run_id}",
                headers=self._user_headers(telegram_id),
                timeout=10,
            )
            r.raise_for_status()
            return r.json()

    async def get_optimization_pdf(
        self, telegram_id: int, run_id: str
    ) -> bytes:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self._base_url}/api/optimize/{run_id}/pdf",
                headers=self._user_headers(telegram_id),
                timeout=30,
            )
            r.raise_for_status()
            return r.content

    async def get_recent_runs(self, telegram_id: int) -> list[dict]:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self._base_url}/api/optimize?limit=5",
                headers=self._user_headers(telegram_id),
            )
            r.raise_for_status()
            return r.json().get("runs", [])

    async def set_default_cv(self, telegram_id: int, cv_id: str) -> None:
        async with httpx.AsyncClient() as client:
            r = await client.patch(
                f"{self._base_url}/api/users/me",
                headers=self._user_headers(telegram_id),
                json={"default_cv_id": cv_id},
            )
            r.raise_for_status()
