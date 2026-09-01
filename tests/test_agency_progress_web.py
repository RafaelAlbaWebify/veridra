# ruff: noqa: E501
from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra.agency_progress_web import router
from veridra.core import Assessment, Finding, Status
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.observations import ObservedAssessment, PageObservation
from veridra.project_store import ClientProject
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_history_store import TenantHistoryStore
from veridra.tenant_project_store import TenantProjectStore

NOW = datetime(2026, 9, 1, 11, 0, tzinfo=UTC)
ANALYST = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.analyst,
    session_id="progress-analyst-session-0001",
    authenticated_at=NOW,
)
VIEWER = RequestIdentity(
    user_id="2" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.viewer,
    session_id="progress-viewer-session-00001",
    authenticated_at=NOW,
)
OTHER = RequestIdentity(
    user_id="3" * 24,
    tenant_id="b" * 24,
    membership_role=TenantRole.viewer,
    session_id="progress-other-session-000001",
    authenticated_at=NOW,
)


def _app(root: Path) -> TestClient:
    app = FastAPI()
    app.state.veridra_tenant_data_root = root

    @app.middleware("http")
    async def identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        role = request.headers.get("x-test-role")
        if role == "viewer":
            bind_verified_request_identity(request, VIEWER)
        elif role == "other":
            bind_verified_request_identity(request, OTHER)
        return await call_next(request)

    app.include_router(router)
    return TestClient(app)


def _finding(
    finding_id: str,
    *,
    status: Status = Status.attention,
    severity: str = "medium",
) -> Finding:
    return Finding(
        id=finding_id,
        area="Website health",
        title=finding_id,
        status=status,
        severity=severity,
        summary="Observed.",
    )


def _page(url: str, fingerprint: str, status: int = 200) -> PageObservation:
    return PageObservation(
        url=url,
        status_code=status,
        depth=0,
        content_type="text/html",
        response_bytes=100,
        title="Example",
        h1_count=1,
        h1_text="Example",
        indexable=True,
        fingerprint=fingerprint,
    )


def _observed(
    generated_at: datetime,
    findings: list[Finding],
    pages: tuple[PageObservation, ...],
) -> ObservedAssessment:
    base = Assessment.build(
        "https://example.com",
        findings,
        generated_at=generated_at,
    )
    return ObservedAssessment.from_assessment(
        base,
        pages=pages,
        collector_version="test",
        crawl_profile="quick",
    )


def _project(tmp_path: Path) -> tuple[Path, str, TenantHistoryStore]:
    root = tmp_path / "tenants"
    project_id = TenantProjectStore(root).save(
        ANALYST,
        ClientProject.build(name="Progress <Client>", target_url="https://example.com"),
    )
    return root, project_id, TenantHistoryStore(root)


def test_progress_surface_shows_exact_latest_vs_previous_deltas(tmp_path: Path) -> None:
    root, project_id, history = _project(tmp_path)
    before = _observed(
        NOW,
        [
            _finding("finding.persist"),
            _finding("finding.resolve"),
            _finding("finding.state", severity="high"),
        ],
        (
            _page("https://example.com/", "a" * 64),
            _page("https://example.com/removed", "b" * 64),
        ),
    )
    after = _observed(
        NOW + timedelta(hours=1),
        [
            _finding("finding.persist"),
            _finding("finding.new"),
            _finding("finding.state", status=Status.passed, severity="info"),
        ],
        (
            _page("https://example.com/", "c" * 64),
            _page("https://example.com/added", "d" * 64),
        ),
    )
    history.save(ANALYST, project_id, before)
    history.save(ANALYST, project_id, after)

    response = _app(root).get(
        f"/agency/projects/{project_id}/progress",
        headers={"x-test-role": "viewer"},
    )

    assert response.status_code == 200
    assert "Progress / Changes for Progress &lt;Client&gt;" in response.text
    assert "Pages added" in response.text
    assert "https://example.com/added" in response.text
    assert "https://example.com/removed" in response.text
    assert "finding.new" in response.text
    assert "finding.resolve" in response.text
    assert "finding.persist" in response.text
    assert "finding.state" in response.text
    assert "attention → passed" in response.text
    assert "high → info" in response.text
    assert "Page-level history is unavailable" not in response.text


def test_progress_surface_marks_legacy_page_history_unknown(tmp_path: Path) -> None:
    root, project_id, history = _project(tmp_path)
    legacy = Assessment.build(
        "https://example.com",
        [_finding("finding.persist")],
        generated_at=NOW,
    )
    current = _observed(
        NOW + timedelta(hours=1),
        [_finding("finding.persist"), _finding("finding.new")],
        (_page("https://example.com/", "a" * 64),),
    )
    history.save(ANALYST, project_id, legacy)
    history.save(ANALYST, project_id, current)

    response = _app(root).get(
        f"/agency/projects/{project_id}/progress",
        headers={"x-test-role": "viewer"},
    )

    assert response.status_code == 200
    assert "Page-level history is unavailable for this comparison" in response.text
    assert "Finding comparison remains valid" in response.text
    assert "finding.new" in response.text


def test_progress_requires_two_assessments(tmp_path: Path) -> None:
    root, project_id, history = _project(tmp_path)
    history.save(
        ANALYST,
        project_id,
        Assessment.build(
            "https://example.com",
            [_finding("finding.one")],
            generated_at=NOW,
        ),
    )

    response = _app(root).get(
        f"/agency/projects/{project_id}/progress",
        headers={"x-test-role": "viewer"},
    )

    assert response.status_code == 200
    assert "At least two saved assessments are required" in response.text


def test_progress_cross_tenant_access_is_concealed(tmp_path: Path) -> None:
    root, project_id, _ = _project(tmp_path)

    response = _app(root).get(
        f"/agency/projects/{project_id}/progress",
        headers={"x-test-role": "other"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found."}
