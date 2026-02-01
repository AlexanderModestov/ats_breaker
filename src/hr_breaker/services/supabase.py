"""Supabase client wrapper for database and storage operations."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from supabase import create_client, Client

from hr_breaker.config import get_settings, logger


class SupabaseError(Exception):
    """Supabase operation error."""

    pass


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

    def update_profile(self, user_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Update user profile."""
        try:
            result = (
                self._client.table("profiles")
                .update(data)
                .eq("id", user_id)
                .execute()
            )
            return result.data[0] if result.data else None
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
