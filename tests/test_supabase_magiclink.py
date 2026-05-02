"""Tests for SupabaseService.generate_magiclink."""

from unittest.mock import MagicMock, patch

import pytest

from hr_breaker.services.supabase import SupabaseError, SupabaseService


@pytest.fixture
def service():
    with patch("hr_breaker.services.supabase.create_client") as mock_create:
        mock_create.return_value = MagicMock()
        svc = SupabaseService()
    return svc


def test_generate_magiclink_returns_token_hash(service):
    response = MagicMock()
    response.properties.hashed_token = "abc123"
    service._client.auth.admin.generate_link = MagicMock(return_value=response)

    token = service.generate_magiclink("user@example.com")

    assert token == "abc123"
    service._client.auth.admin.generate_link.assert_called_once_with(
        {"type": "magiclink", "email": "user@example.com"}
    )


def test_generate_magiclink_raises_on_admin_failure(service):
    service._client.auth.admin.generate_link = MagicMock(
        side_effect=Exception("admin call failed")
    )

    with pytest.raises(SupabaseError):
        service.generate_magiclink("user@example.com")
