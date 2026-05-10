"""Tests for /api/optimize PATCH route (manual title/company fix)."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from hr_breaker.api.deps import (
    get_current_user,
    get_current_user_email,
    get_supabase_service,
)
from hr_breaker.api.main import app

USER = "user-uuid"
EMAIL = "user@example.com"
RUN_ID = "run-uuid"


def _profile() -> dict:
    return {
        "id": USER,
        "subscription_tier": "free",
        "subscription_status": "active",
        "current_period_end": None,
    }


def _run(status: str = "complete", needs_review: list[str] | None = None) -> dict:
    return {
        "id": RUN_ID,
        "user_id": USER,
        "status": status,
        "job_parsed": {
            "title": "Original Title",
            "company": "Not Specified",
            "location": "Remote",
            "requirements": [],
            "responsibilities": [],
            "keywords": [],
            "needs_review": needs_review if needs_review is not None else ["company"],
        },
        "created_at": "2026-05-10T00:00:00+00:00",
        "iterations": 1,
        "current_step": None,
        "feedback": None,
        "result_html": None,
        "error": None,
        "timing": None,
        "first_name": None,
        "last_name": None,
    }


@pytest.fixture
def fake_supabase():
    svc = MagicMock()
    svc.get_optimization_run.return_value = _run()
    svc.update_optimization_run.return_value = None
    svc.get_profile.return_value = _profile()
    return svc


@pytest.fixture
def client(fake_supabase):
    app.dependency_overrides[get_supabase_service] = lambda: fake_supabase
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_current_user_email] = lambda: (USER, EMAIL)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_patch_updates_company_and_clears_needs_review(client, fake_supabase):
    resp = client.patch(
        f"/api/optimize/{RUN_ID}/job",
        json={"company": "Acme Corp"},
    )
    assert resp.status_code == 200
    update_call = fake_supabase.update_optimization_run.call_args
    run_id_arg, payload = update_call[0]
    assert run_id_arg == RUN_ID
    assert payload["job_parsed"]["company"] == "Acme Corp"
    assert payload["job_parsed"]["title"] == "Original Title"  # unchanged
    assert "company" not in payload["job_parsed"]["needs_review"]


def test_patch_updates_both_fields(client, fake_supabase):
    fake_supabase.get_optimization_run.return_value = _run(
        needs_review=["title", "company"]
    )
    resp = client.patch(
        f"/api/optimize/{RUN_ID}/job",
        json={"title": "Senior Eng", "company": "Acme"},
    )
    assert resp.status_code == 200
    payload = fake_supabase.update_optimization_run.call_args[0][1]
    assert payload["job_parsed"]["title"] == "Senior Eng"
    assert payload["job_parsed"]["company"] == "Acme"
    assert payload["job_parsed"]["needs_review"] == []


def test_patch_strips_whitespace(client, fake_supabase):
    resp = client.patch(
        f"/api/optimize/{RUN_ID}/job",
        json={"company": "  Acme  "},
    )
    assert resp.status_code == 200
    payload = fake_supabase.update_optimization_run.call_args[0][1]
    assert payload["job_parsed"]["company"] == "Acme"


def test_patch_rejects_empty_company(client):
    resp = client.patch(f"/api/optimize/{RUN_ID}/job", json={"company": "   "})
    assert resp.status_code == 422


def test_patch_rejects_too_long(client):
    resp = client.patch(
        f"/api/optimize/{RUN_ID}/job",
        json={"title": "x" * 201},
    )
    assert resp.status_code == 422


def test_patch_requires_at_least_one_field(client):
    resp = client.patch(f"/api/optimize/{RUN_ID}/job", json={})
    assert resp.status_code == 422


def test_patch_404_when_run_missing(client, fake_supabase):
    fake_supabase.get_optimization_run.return_value = None
    resp = client.patch(
        f"/api/optimize/{RUN_ID}/job",
        json={"company": "Acme"},
    )
    assert resp.status_code == 404


def test_patch_blocked_while_parsing(client, fake_supabase):
    fake_supabase.get_optimization_run.return_value = _run(status="parse_job")
    resp = client.patch(
        f"/api/optimize/{RUN_ID}/job",
        json={"company": "Acme"},
    )
    assert resp.status_code == 409


def test_patch_unauthenticated_returns_401():
    app.dependency_overrides.clear()
    c = TestClient(app)
    resp = c.patch(f"/api/optimize/{RUN_ID}/job", json={"company": "Acme"})
    assert resp.status_code == 401
