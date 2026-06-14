"""Tests for /api/optimize PATCH route (manual title/company fix)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from hr_breaker.api.deps import (
    get_current_user,
    get_current_user_email,
    get_supabase_service,
)
from hr_breaker.api.main import app
from hr_breaker.api.routes.optimize import _run_optimization
from hr_breaker.models.audit import AuditScore
from hr_breaker.models.resume import OptimizedResume
from hr_breaker.services import ScrapedJob

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


# ---------------------------------------------------------------------------
# _run_optimization: audit score is persisted when optimized.audit is set
# ---------------------------------------------------------------------------

_AUDIT = AuditScore(
    ats_compatibility="ATS-Ready",
    recruiter_scan="Strong",
    bullet_quality="Strong",
    seniority_calibration="Aligned",
    keyword_coverage="Strong",
    structure="Strong",
    concern_management="NA",
    consistency="Strong",
    overall="Strong",
    top_fixes=["Fix X", "Fix Y"],
)


@pytest.mark.asyncio
async def test_run_optimization_persists_audit():
    """When optimize_for_job returns an OptimizedResume with audit set,
    the final update_optimization_run call must include the serialized audit."""
    optimized = OptimizedResume(source_checksum="abc", html="<p>hi</p>", audit=_AUDIT)

    mock_validation = MagicMock()
    mock_validation.passed = True

    mock_job = MagicMock()
    mock_job.title = "Engineer"
    mock_job.company = "Acme"
    mock_job.location = "Remote"
    mock_job.requirements = []
    mock_job.responsibilities = []
    mock_job.keywords = []

    fake_supa = MagicMock()
    fake_supa.upload_result_pdf.side_effect = Exception("no pdf")

    with (
        patch(
            "hr_breaker.api.routes.optimize.parse_job_posting",
            new=AsyncMock(return_value=(mock_job, [])),
        ),
        patch(
            "hr_breaker.api.routes.optimize.extract_name",
            new=AsyncMock(return_value=("Jane", "Doe")),
        ),
        patch(
            "hr_breaker.api.routes.optimize.optimize_for_job",
            new=AsyncMock(return_value=(optimized, mock_validation, None)),
        ),
        patch("hr_breaker.api.routes.optimize.capture"),
        patch(
            "hr_breaker.api.routes.optimize.scrape_job_posting",
            return_value=ScrapedJob(text="job text", hints=None),
        ),
    ):
        await _run_optimization(
            run_id=RUN_ID,
            user_id=USER,
            cv_content="my cv",
            job_input="https://example.com/job",
            max_iterations=1,
            parallel=False,
            supabase=fake_supa,
        )

    # Find the "complete" update call
    complete_call = next(
        call
        for call in fake_supa.update_optimization_run.call_args_list
        if call[0][1].get("status") == "complete"
    )
    payload = complete_call[0][1]
    assert payload["audit"] == _AUDIT.model_dump()


# ---------------------------------------------------------------------------
# POST /api/optimize: metered quota consume
# ---------------------------------------------------------------------------


class TestOptimizeQuota:
    @pytest.fixture(autouse=True)
    def _no_admins(self):
        with patch("hr_breaker.services.access_control.get_settings") as s:
            s.return_value.unlimited_users = []
            yield

    def test_free_at_limit_returns_402(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = {
            "id": USER, "subscription_tier": "free", "subscription_status": "none",
            "current_period_end": None, "period_request_count": 3,
        }
        r = client.post("/api/optimize", json={"cv_id": "c1", "job_input": "..."})
        assert r.status_code == 402
        assert r.json()["detail"]["reason"] == "quota_exhausted"
        fake_supabase.consume_optimization_quota.assert_not_called()

    def test_consume_called_then_run_starts(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = {
            "id": USER, "subscription_tier": "job_hunter",
            "subscription_status": "active",
            "current_period_end": "2099-01-01T00:00:00+00:00",
            "period_request_count": 5,
        }
        fake_supabase.consume_optimization_quota.return_value = True
        fake_supabase.get_cv.return_value = {"id": "c1", "content_text": "cv"}
        fake_supabase.create_optimization_run.return_value = {"id": "r1"}
        r = client.post("/api/optimize", json={"cv_id": "c1", "job_input": "..."})
        assert r.status_code == 200
        fake_supabase.consume_optimization_quota.assert_called_once_with(USER, 20)
        fake_supabase.create_optimization_run.assert_called_once()

    def test_lost_race_returns_402(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = {
            "id": USER, "subscription_tier": "free", "subscription_status": "none",
            "current_period_end": None, "period_request_count": 2,
        }
        fake_supabase.consume_optimization_quota.return_value = False  # raced to limit
        fake_supabase.get_cv.return_value = {"id": "c1", "content_text": "cv"}
        r = client.post("/api/optimize", json={"cv_id": "c1", "job_input": "..."})
        assert r.status_code == 402
        fake_supabase.create_optimization_run.assert_not_called()
