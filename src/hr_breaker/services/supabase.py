"""Supabase client wrapper for database and storage operations."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from supabase import create_client, Client

from hr_breaker.config import get_settings, logger


class SupabaseError(Exception):
    """Supabase operation error."""

    pass


def _preview_and_count(raw_messages: list) -> tuple[str | None, int]:
    """Return (first user message preview, total user+assistant count)."""
    from pydantic_ai import ModelMessagesTypeAdapter
    from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

    if not raw_messages:
        return None, 0
    try:
        messages = ModelMessagesTypeAdapter.validate_python(raw_messages)
    except Exception:
        return None, 0

    preview = None
    count = 0
    for msg in messages:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, UserPromptPart):
                    count += 1
                    if preview is None:
                        text = part.content if isinstance(part.content, str) else str(part.content)
                        preview = text.strip()[:80] or None
        elif isinstance(msg, ModelResponse):
            if any(isinstance(p, TextPart) for p in msg.parts):
                count += 1
    return preview, count


class SupabaseService:
    """Wrapper for Supabase database and storage operations."""

    def __init__(self):
        settings = get_settings()
        if not settings.supabase_url or not settings.supabase_service_key:
            raise SupabaseError("Supabase URL and service key are required")

        self._client: Client = create_client(
            settings.supabase_url,
            settings.supabase_service_key,
        )

    @property
    def client(self) -> Client:
        """Get the Supabase client."""
        return self._client

    # Profile operations
    def get_profile(self, user_id: str) -> dict[str, Any] | None:
        """Get user profile by ID."""
        try:
            result = (
                self._client.table("profiles")
                .select("*")
                .eq("id", user_id)
                .single()
                .execute()
            )
            return result.data
        except Exception as e:
            logger.warning(f"Failed to get profile: {e}")
            return None

    def update_profile(self, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update user profile. Raises SupabaseError if no matching profile found."""
        try:
            result = (
                self._client.table("profiles")
                .update(data)
                .eq("id", user_id)
                .execute()
            )
            if not result.data:
                raise SupabaseError(f"No profile found for user_id={user_id}")
            return result.data[0]
        except SupabaseError:
            raise
        except Exception as e:
            logger.error(f"Failed to update profile: {e}")
            raise SupabaseError(f"Failed to update profile: {e}") from e

    def create_profile(self, user_id: str, email: str, name: str | None = None) -> dict[str, Any]:
        """Create user profile."""
        try:
            result = (
                self._client.table("profiles")
                .insert({
                    "id": user_id,
                    "email": email,
                    "name": name,
                    "theme": "minimal",
                })
                .execute()
            )
            return result.data[0]
        except Exception as e:
            logger.error(f"Failed to create profile: {e}")
            raise SupabaseError(f"Failed to create profile: {e}") from e

    # CV operations
    def list_cvs(self, user_id: str) -> list[dict[str, Any]]:
        """List all CVs for a user."""
        try:
            result = (
                self._client.table("cvs")
                .select("id, name, original_filename, created_at")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .execute()
            )
            return result.data
        except Exception as e:
            logger.error(f"Failed to list CVs: {e}")
            raise SupabaseError(f"Failed to list CVs: {e}") from e

    def get_cv(self, cv_id: str, user_id: str) -> dict[str, Any] | None:
        """Get a CV by ID (with user ownership check)."""
        try:
            result = (
                self._client.table("cvs")
                .select("*")
                .eq("id", cv_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )
            return result.data
        except Exception as e:
            logger.warning(f"Failed to get CV: {e}")
            return None

    def create_cv(
        self,
        user_id: str,
        name: str,
        file_path: str,
        original_filename: str,
        content_text: str,
    ) -> dict[str, Any]:
        """Create a new CV record."""
        cv_id = str(uuid4())
        try:
            result = (
                self._client.table("cvs")
                .insert({
                    "id": cv_id,
                    "user_id": user_id,
                    "name": name,
                    "file_path": file_path,
                    "original_filename": original_filename,
                    "content_text": content_text,
                })
                .execute()
            )
            return result.data[0]
        except Exception as e:
            logger.error(f"Failed to create CV: {e}")
            raise SupabaseError(f"Failed to create CV: {e}") from e

    def delete_cv(self, cv_id: str, user_id: str) -> bool:
        """Delete a CV (with user ownership check)."""
        try:
            # First get the CV to check ownership and get file path
            cv = self.get_cv(cv_id, user_id)
            if not cv:
                return False

            # Delete from database
            self._client.table("cvs").delete().eq("id", cv_id).execute()

            # Delete from storage
            if cv.get("file_path"):
                try:
                    self._client.storage.from_("cvs").remove([cv["file_path"]])
                except Exception as e:
                    logger.warning(f"Failed to delete CV file from storage: {e}")

            return True
        except Exception as e:
            logger.error(f"Failed to delete CV: {e}")
            raise SupabaseError(f"Failed to delete CV: {e}") from e

    # Storage operations
    def upload_cv_file(
        self,
        user_id: str,
        file_content: bytes,
        filename: str,
    ) -> str:
        """
        Upload a CV file to Supabase Storage.

        Returns:
            The storage path of the uploaded file
        """
        cv_id = str(uuid4())
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "txt"
        file_path = f"{user_id}/cvs/{cv_id}.{ext}"

        try:
            self._client.storage.from_("cvs").upload(
                file_path,
                file_content,
                file_options={"content-type": self._get_content_type(ext)},
            )
            return file_path
        except Exception as e:
            logger.error(f"Failed to upload CV file: {e}")
            raise SupabaseError(f"Failed to upload CV file: {e}") from e

    def download_cv_file(self, file_path: str) -> bytes:
        """Download a CV file from storage."""
        try:
            response = self._client.storage.from_("cvs").download(file_path)
            return response
        except Exception as e:
            logger.error(f"Failed to download CV file: {e}")
            raise SupabaseError(f"Failed to download CV file: {e}") from e

    # Optimization run operations
    def create_optimization_run(
        self,
        user_id: str,
        cv_id: str,
        job_input: str,
    ) -> dict[str, Any]:
        """Create a new optimization run."""
        run_id = str(uuid4())
        try:
            result = (
                self._client.table("optimization_runs")
                .insert({
                    "id": run_id,
                    "user_id": user_id,
                    "cv_id": cv_id,
                    "job_input": job_input,
                    "status": "pending",
                    "iterations": 0,
                })
                .execute()
            )
            return result.data[0]
        except Exception as e:
            logger.error(f"Failed to create optimization run: {e}")
            raise SupabaseError(f"Failed to create optimization run: {e}") from e

    def get_optimization_run(self, run_id: str, user_id: str) -> dict[str, Any] | None:
        """Get an optimization run by ID (with user ownership check)."""
        try:
            result = (
                self._client.table("optimization_runs")
                .select("*")
                .eq("id", run_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )
            return result.data
        except Exception as e:
            logger.warning(f"Failed to get optimization run: {e}")
            return None

    def list_optimization_runs(self, user_id: str) -> list[dict[str, Any]]:
        """List all optimization runs for a user."""
        try:
            result = (
                self._client.table("optimization_runs")
                .select("id, status, job_parsed, created_at")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .execute()
            )
            return result.data
        except Exception as e:
            logger.error(f"Failed to list optimization runs: {e}")
            raise SupabaseError(f"Failed to list optimization runs: {e}") from e

    def update_optimization_run(self, run_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Update an optimization run."""
        try:
            result = (
                self._client.table("optimization_runs")
                .update(data)
                .eq("id", run_id)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to update optimization run: {e}")
            raise SupabaseError(f"Failed to update optimization run: {e}") from e

    def upload_result_pdf(self, run_id: str, user_id: str, pdf_bytes: bytes) -> str:
        """Upload result PDF to storage."""
        file_path = f"{user_id}/results/{run_id}.pdf"
        try:
            self._client.storage.from_("results").upload(
                file_path,
                pdf_bytes,
                file_options={"content-type": "application/pdf"},
            )
            return file_path
        except Exception as e:
            logger.error(f"Failed to upload result PDF: {e}")
            raise SupabaseError(f"Failed to upload result PDF: {e}") from e

    def download_result_pdf(self, file_path: str) -> bytes:
        """Download result PDF from storage."""
        try:
            response = self._client.storage.from_("results").download(file_path)
            return response
        except Exception as e:
            logger.error(f"Failed to download result PDF: {e}")
            raise SupabaseError(f"Failed to download result PDF: {e}") from e

    def delete_result_pdf(self, file_path: str) -> None:
        """Delete result PDF from storage."""
        try:
            self._client.storage.from_("results").remove([file_path])
        except Exception as e:
            logger.error(f"Failed to delete result PDF: {e}")
            raise SupabaseError(f"Failed to delete result PDF: {e}") from e

    def delete_optimization_run(self, run_id: str) -> None:
        """Delete an optimization run."""
        try:
            self._client.table("optimization_runs").delete().eq("id", run_id).execute()
        except Exception as e:
            logger.error(f"Failed to delete optimization run: {e}")
            raise SupabaseError(f"Failed to delete optimization run: {e}") from e

    # Coach session operations
    def create_coach_session(
        self,
        user_id: str,
        optimization_run_id: str,
    ) -> dict[str, Any]:
        """Create a new coach session (thread)."""
        try:
            session_id = str(uuid4())
            result = (
                self._client.table("coach_sessions")
                .insert({
                    "id": session_id,
                    "user_id": user_id,
                    "optimization_run_id": optimization_run_id,
                })
                .execute()
            )
            return result.data[0]
        except Exception as e:
            logger.error(f"Failed to create coach session: {e}")
            raise SupabaseError(f"Failed to create coach session: {e}") from e

    def get_coach_session(
        self, session_id: str, user_id: str
    ) -> dict[str, Any] | None:
        """Return coach session if it belongs to user, else None."""
        try:
            result = (
                self._client.table("coach_sessions")
                .select("*")
                .eq("id", session_id)
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to get coach session: {e}")
            raise SupabaseError(f"Failed to get coach session: {e}") from e

    def update_coach_session_title(
        self, session_id: str, user_id: str, title: str | None
    ) -> dict[str, Any] | None:
        """Update session title with ownership check."""
        try:
            result = (
                self._client.table("coach_sessions")
                .update({"title": title})
                .eq("id", session_id)
                .eq("user_id", user_id)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to update coach session: {e}")
            raise SupabaseError(f"Failed to update coach session: {e}") from e

    def delete_coach_session(self, session_id: str, user_id: str) -> bool:
        """Delete coach session (cascades to messages). Returns True if removed."""
        try:
            result = (
                self._client.table("coach_sessions")
                .delete()
                .eq("id", session_id)
                .eq("user_id", user_id)
                .execute()
            )
            return bool(result.data)
        except Exception as e:
            logger.error(f"Failed to delete coach session: {e}")
            raise SupabaseError(f"Failed to delete coach session: {e}") from e

    def list_coach_sessions(self, user_id: str) -> list[dict[str, Any]]:
        """List all coach sessions for a user with preview + message_count."""
        try:
            sessions = (
                self._client.table("coach_sessions")
                .select("id, optimization_run_id, title, last_message_at, created_at, updated_at")
                .eq("user_id", user_id)
                .order("last_message_at", desc=True, nullsfirst=False)
                .execute()
            ).data

            if not sessions:
                return []

            # Bulk-fetch messages for all sessions in one round-trip.
            ids = [s["id"] for s in sessions]
            msg_rows = (
                self._client.table("coach_messages")
                .select("session_id, messages")
                .in_("session_id", ids)
                .execute()
            ).data
            by_session = {row["session_id"]: row.get("messages") or [] for row in msg_rows}

            for s in sessions:
                raw = by_session.get(s["id"], [])
                preview, count = _preview_and_count(raw)
                s["preview"] = preview
                s["message_count"] = count
            return sessions
        except Exception as e:
            logger.error(f"Failed to list coach sessions: {e}")
            raise SupabaseError(f"Failed to list coach sessions: {e}") from e

    # Coach message operations
    def get_coach_messages(self, session_id: str) -> list:
        """Get messages for a coach session."""
        try:
            result = (
                self._client.table("coach_messages")
                .select("messages")
                .eq("session_id", session_id)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0].get("messages", [])
            return []
        except Exception as e:
            logger.error(f"Failed to get coach messages: {e}")
            raise SupabaseError(f"Failed to get coach messages: {e}") from e

    def save_coach_messages(self, session_id: str, messages: list) -> None:
        """Upsert coach messages and touch session updated_at."""
        try:
            now = datetime.now().isoformat()
            # Upsert messages row
            self._client.table("coach_messages").upsert(
                {
                    "session_id": session_id,
                    "messages": messages,
                    "updated_at": now,
                },
                on_conflict="session_id",
            ).execute()

            # Touch coach_sessions.updated_at and last_message_at
            self._client.table("coach_sessions").update(
                {"updated_at": now, "last_message_at": now}
            ).eq("id", session_id).execute()
        except Exception as e:
            logger.error(f"Failed to save coach messages: {e}")
            raise SupabaseError(f"Failed to save coach messages: {e}") from e

    # Storybank operations
    def list_storybank(self, user_id: str) -> list[dict[str, Any]]:
        """List all storybank entries for a user."""
        try:
            result = (
                self._client.table("storybank_entries")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .execute()
            )
            return result.data
        except Exception as e:
            logger.error(f"Failed to list storybank entries: {e}")
            raise SupabaseError(f"Failed to list storybank entries: {e}") from e

    def create_storybank_entry(
        self, user_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a new storybank entry."""
        try:
            result = (
                self._client.table("storybank_entries")
                .insert({**data, "user_id": user_id})
                .execute()
            )
            return result.data[0]
        except Exception as e:
            logger.error(f"Failed to create storybank entry: {e}")
            raise SupabaseError(f"Failed to create storybank entry: {e}") from e

    def update_storybank_entry(
        self, entry_id: str, user_id: str, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update a storybank entry with ownership check."""
        try:
            result = (
                self._client.table("storybank_entries")
                .update({**data, "updated_at": datetime.now().isoformat()})
                .eq("id", entry_id)
                .eq("user_id", user_id)
                .execute()
            )
            if not result.data:
                return None
            return result.data[0]
        except Exception as e:
            logger.error(f"Failed to update storybank entry: {e}")
            raise SupabaseError(f"Failed to update storybank entry: {e}") from e

    def delete_storybank_entry(self, entry_id: str, user_id: str) -> bool:
        """Delete a storybank entry with ownership check."""
        try:
            result = (
                self._client.table("storybank_entries")
                .delete()
                .eq("id", entry_id)
                .eq("user_id", user_id)
                .execute()
            )
            return len(result.data) > 0
        except Exception as e:
            logger.error(f"Failed to delete storybank entry: {e}")
            raise SupabaseError(f"Failed to delete storybank entry: {e}") from e

    # Subscription operations
    def consume_request_atomic(
        self,
        user_id: str,
        is_subscriber: bool,
        subscription_limit: int = 50,
    ) -> bool:
        """
        Atomically consume a request from user's quota.

        Uses PostgreSQL function for atomic update to prevent race conditions.

        Args:
            user_id: The user's ID
            is_subscriber: Whether user has active subscription
            subscription_limit: Max requests per subscription period

        Returns:
            True if request was consumed, False if no quota available
        """
        try:
            result = self._client.rpc(
                "consume_request",
                {
                    "p_user_id": user_id,
                    "p_is_subscriber": is_subscriber,
                    "p_subscription_limit": subscription_limit,
                }
            ).execute()

            return result.data is True
        except Exception as e:
            logger.error(f"Failed to consume request: {e}")
            raise SupabaseError(f"Failed to consume request: {e}") from e

    def add_addon_credits_atomic(self, user_id: str, credits_to_add: int) -> bool:
        """
        Atomically add addon credits to user's account.

        Args:
            user_id: The user's ID
            credits_to_add: Number of credits to add

        Returns:
            True if credits were added successfully
        """
        try:
            result = self._client.rpc(
                "add_addon_credits",
                {
                    "p_user_id": user_id,
                    "p_credits": credits_to_add,
                }
            ).execute()

            return result.data is True
        except Exception as e:
            logger.error(f"Failed to add addon credits: {e}")
            raise SupabaseError(f"Failed to add addon credits: {e}") from e

    def get_profile_by_telegram_id(self, telegram_id: int) -> dict[str, Any] | None:
        """Get user profile by Telegram ID."""
        try:
            result = (
                self._client.table("profiles")
                .select("*")
                .eq("telegram_id", telegram_id)
                .single()
                .execute()
            )
            return result.data
        except Exception:
            return None

    def link_telegram(self, user_id: str, telegram_id: int) -> None:
        """Link a Telegram ID to a user profile."""
        try:
            self._client.table("profiles").update(
                {"telegram_id": telegram_id}
            ).eq("id", user_id).execute()
        except Exception as e:
            raise SupabaseError(f"Failed to link Telegram: {e}") from e

    def generate_magiclink(self, email: str) -> str:
        """Generate a Supabase magic-link token_hash for the given email.

        The frontend exchanges this hash via ``supabase.auth.verifyOtp`` to set
        a real Supabase session. Used for trusted server-side login (e.g. after
        validating Telegram WebApp initData).
        """
        try:
            response = self._client.auth.admin.generate_link(
                {"type": "magiclink", "email": email}
            )
            return response.properties.hashed_token
        except Exception as e:
            logger.error(f"Failed to generate magic link: {e}")
            raise SupabaseError(f"Failed to generate magic link: {e}") from e

    def set_pending_signin_message(
        self, telegram_id: int, chat_id: int, message_id: int
    ) -> None:
        """Record the "Sign in" message id so it can be edited after linking."""
        try:
            self._client.table("pending_signin_messages").upsert(
                {
                    "telegram_id": telegram_id,
                    "chat_id": chat_id,
                    "message_id": message_id,
                },
                on_conflict="telegram_id",
            ).execute()
        except Exception as e:
            logger.warning(f"Failed to set pending signin message: {e}")

    def pop_pending_signin_message(
        self, telegram_id: int
    ) -> dict[str, Any] | None:
        """Fetch and delete the pending sign-in message for a telegram id."""
        try:
            select_result = (
                self._client.table("pending_signin_messages")
                .select("telegram_id, chat_id, message_id")
                .eq("telegram_id", telegram_id)
                .limit(1)
                .execute()
            )
            if not select_result.data:
                return None
            row = select_result.data[0]
            self._client.table("pending_signin_messages").delete().eq(
                "telegram_id", telegram_id
            ).execute()
            return row
        except Exception as e:
            logger.warning(f"Failed to pop pending signin message: {e}")
            return None

    def get_default_cv(self, user_id: str) -> dict[str, Any] | None:
        """Get the user's default CV (most recently uploaded)."""
        try:
            result = (
                self._client.table("cvs")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if not result.data:
                return None
            profile = self.get_profile(user_id)
            if profile and profile.get("default_cv_id"):
                cv = (
                    self._client.table("cvs")
                    .select("*")
                    .eq("id", profile["default_cv_id"])
                    .single()
                    .execute()
                )
                return cv.data if cv.data else result.data[0]
            return result.data[0]
        except Exception:
            return None

    def get_recent_runs(self, user_id: str, limit: int = 5) -> list[dict[str, Any]]:
        """Get recent optimization runs for a user."""
        try:
            result = (
                self._client.table("optimization_runs")
                .select("id, job_title, job_company, status, created_at")
                .eq("user_id", user_id)
                .eq("status", "completed")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data or []
        except Exception:
            return []

    @staticmethod
    def _get_content_type(ext: str) -> str:
        """Get content type for file extension."""
        content_types = {
            "pdf": "application/pdf",
            "txt": "text/plain",
            "tex": "text/x-tex",
            "md": "text/markdown",
            "html": "text/html",
        }
        return content_types.get(ext.lower(), "application/octet-stream")
