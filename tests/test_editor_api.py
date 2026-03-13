"""Tests for the resume editor API routes."""

import pytest
from fastapi import HTTPException

from hr_breaker.api.routes.editor import _get_completed_run


def test_get_completed_run_not_found():
    """Test helper raises 404 when run not found."""

    class FakeSupabase:
        def get_optimization_run(self, run_id, user_id):
            return None

    with pytest.raises(HTTPException) as exc_info:
        _get_completed_run("fake-id", "fake-user", FakeSupabase())
    assert exc_info.value.status_code == 404


def test_get_completed_run_not_complete():
    """Test helper raises 400 when run not complete."""

    class FakeSupabase:
        def get_optimization_run(self, run_id, user_id):
            return {"status": "pending"}

    with pytest.raises(HTTPException) as exc_info:
        _get_completed_run("fake-id", "fake-user", FakeSupabase())
    assert exc_info.value.status_code == 400


def test_get_completed_run_success():
    """Test helper returns run when complete."""

    class FakeSupabase:
        def get_optimization_run(self, run_id, user_id):
            return {"status": "complete", "result_html": "<p>test</p>"}

    run = _get_completed_run("fake-id", "fake-user", FakeSupabase())
    assert run["status"] == "complete"
