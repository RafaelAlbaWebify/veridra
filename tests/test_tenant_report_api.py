from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

import veridra.tenant_report_api as tenant_report_api
from veridra.core import Assessment, Finding, Status
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.pdf_reports import PdfDocument
from veridra.project_store import ClientProject
from veridra.report_profiles import ReportProfile
from veridra.request_security import bind_verified_request_identity
from veridra.runtime_config import RuntimeConfig, RuntimeEnvironment
from veridra.tenant_assessment_approval_store import TenantAssessmentApprovalStore
from veridra.tenant_history_store import TenantHistoryStore
from veridra.tenant_profile_store import TenantProfileStore
from veridra.tenant_project_store import TenantProjectStore
from veridra.tenant_report_api import router
from veridra.tenant_workspace_policy import TenantWorkspacePolicy
from veridra.workspace_enforcement import enforce_workspace_policy
from veridra.workspace_policy import (
    PlanName,
    UsageKind,
    WorkspaceConfig,
    WorkspaceStore,
    usage_period,
)

NOW = datetime(2026, 7, 26, 0, 0, tzinfo=UTC)


def _identity(tenant_id: str, role: TenantRole) -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id=tenant_id,
        membership_role=role,
        session_id="b" * 24,
        authenticated_at=NOW,
    )


def _assessment() -> Assessment:
    return Assessment.build(
        "https://example.com",
        [
            Finding(
                id="security.hsts",
                area="Security posture",
                title="Enable HSTS",
                status=Status.attention,
                severity="medium",
                summary="HSTS is missing.",
                recommendation="Enable HSTS.",
            )
        ],
        generated_at=NOW,
    )


def _client(
    root: Path,
    identity: RequestIdentity,
    *,
    production: bool = False,
    commercial_middleware: bool = False,
) -> TestClient:
    app = FastAPI()
    app.state.veridra_tenant_data_root = root
    if production:
        app.state.veridra_runtime_config = RuntimeConfig(
            environment=RuntimeEnvironment.production,
            identity_database=root.parent / "identity.sqlite3",
            tenant_data_root=root,
            trusted_origin="https://app.example.com",
            allowed_hosts=("app.example.com",),
            trusted_proxy_ips=(),
            max_request_body_bytes=1_000_000,
            bind_host="0.0.0.0",
            bind_port=8443,
        )

    if commercial_middleware:
        app.middleware("http")(enforce_workspace_policy)

    @app.middleware("http")
    async def identity_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        bind_verified_request_identity(request, identity)
        return await call_next(request)

    app.include_router(router)
    return TestClient(app)


def _default_sources(root: Path, identity: RequestIdentity) -> tuple[str, str]:
    project_id = TenantProjectStore(root).save(
        identity,
        ClientProject.build(
            name="Default report project",
            target_url="https://example.com",
        ),
    )
    assessment_id = TenantHistoryStore(root).save(
        identity,
        project_id,
        _assessment(),
    )
    TenantAssessmentApprovalStore(root).approve(identity, project_id, assessment_id)
    return project_id, assessment_id


def _sources(root: Path, identity: RequestIdentity) -> tuple[str, str]:
    profile_id = TenantProfileStore(root).save(
        identity,
        ReportProfile(organisation_name="Tenant Agency"),
    )
    project_id = TenantProjectStore(root).save(
        identity,
        ClientProject.build(
            name="Tenant project",
            target_url="https://example.com",
            profile_id=profile_id,
        ),
    )
    assessment_id = TenantHistoryStore(root).save(
        identity,
        project_id,
        _assessment(),
    )
    TenantAssessmentApprovalStore(root).approve(identity, project_id, assessment_id)
    return project_id, assessment_id


def test_html_and_export_use_tenant_sources_only(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    identity = _identity("1" * 24, TenantRole.analyst)
    project_id, assessment_id = _sources(root, identity)
    client = _client(root, identity)
    base = f"/api/tenant/projects/{project_id}/assessments/{assessment_id}"

    report = client.get(f"{base}/report")
    export = client.get(f"{base}/export")

    assert report.status_code == 200
    assert "Tenant Agency" in report.text
    assert "Enable HSTS" in report.text
    assert export.status_code == 200
    assert export.headers["content-type"] == "application/zip"
    assert export.content.startswith(b"PK")
    assert not (tmp_path / "history").exists()
    assert not (tmp_path / "profiles").exists()
    assert not (tmp_path / "projects").exists()


def test_viewer_cannot_generate_reports(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    analyst = _identity("2" * 24, TenantRole.analyst)
    viewer = _identity("2" * 24, TenantRole.viewer)
    project_id, assessment_id = _sources(root, analyst)

    response = _client(root, viewer).get(
        f"/api/tenant/projects/{project_id}/assessments/{assessment_id}/report"
    )

    assert response.status_code == 403


def test_other_tenant_cannot_discover_report_sources(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    owner = _identity("3" * 24, TenantRole.analyst)
    outsider = _identity("4" * 24, TenantRole.analyst)
    project_id, assessment_id = _sources(root, owner)

    response = _client(root, outsider).get(
        f"/api/tenant/projects/{project_id}/assessments/{assessment_id}/report"
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Report source not found."}



def test_pdf_endpoint_passes_affected_pages_to_renderer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "tenants"
    identity = _identity("5" * 24, TenantRole.analyst)
    profile_id = TenantProfileStore(root).save(
        identity,
        ReportProfile(organisation_name="Tenant Agency"),
    )
    project_id = TenantProjectStore(root).save(
        identity,
        ClientProject.build(
            name="Tenant project",
            target_url="https://example.com",
            profile_id=profile_id,
        ),
    )
    affected_url = "https://example.com/contact"
    assessment = Assessment.build(
        "https://example.com",
        [
            Finding(
                id="crawl.title",
                area="Search visibility",
                title="Document title",
                status=Status.attention,
                severity="medium",
                summary="One crawled page needs attention.",
                evidence={"affected_urls": [affected_url]},
            )
        ],
        generated_at=NOW,
    )
    assessment_id = TenantHistoryStore(root).save(
        identity,
        project_id,
        assessment,
    )
    TenantAssessmentApprovalStore(root).approve(identity, project_id, assessment_id)
    captured: dict[str, str] = {}

    def fake_render_pdf(report_html: str, *, target: str) -> PdfDocument:
        captured["html"] = report_html
        captured["target"] = target
        return PdfDocument(b"%PDF-test", "tenant-report.pdf")

    monkeypatch.setattr(tenant_report_api, "render_pdf", fake_render_pdf)
    client = _client(root, identity)
    response = client.get(
        f"/api/tenant/projects/{project_id}/assessments/{assessment_id}/report.pdf"
    )

    assert response.status_code == 200
    assert "Affected pages" in captured["html"]
    assert affected_url in captured["html"]
    assert captured["target"] == "https://example.com/"



def test_spanish_representative_assessment_reaches_pdf_renderer_localized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "tenants"
    identity = _identity("6" * 24, TenantRole.analyst)
    profile_id = TenantProfileStore(root).save(
        identity,
        ReportProfile(
            organisation_name="Agencia Ejemplo",
            client_name="Cliente Ejemplo",
            language="es",
        ),
    )
    project_id = TenantProjectStore(root).save(
        identity,
        ClientProject.build(
            name="Proyecto español",
            target_url="https://example.com",
            profile_id=profile_id,
        ),
    )
    findings = [
        Finding(
            id="crawl.title",
            area="Search visibility",
            title="Multi-page document title",
            status=Status.attention,
            severity="medium",
            summary="1 of 3 crawled HTML pages need attention.",
            recommendation="Review and correct the affected pages for document title.",
            evidence={"affected_urls": ["https://example.com/contact"], "crawled_pages": 3},
        ),
        Finding(
            id="accessibility.form-labels",
            area="Accessibility",
            title="Detectable form labels",
            status=Status.attention,
            severity="high",
            summary="1 crawled pages contain form controls without a detectable label.",
            recommendation="Associate visible labels with every form control.",
            evidence={"affected_urls": ["https://example.com/contact"]},
        ),
        Finding(
            id="security.insecure-resources",
            area="Security posture",
            title="Insecure active resources",
            status=Status.attention,
            severity="high",
            summary="1 crawled pages reference active HTTP subresources.",
            recommendation="Move active public subresources to HTTPS.",
            evidence={"affected_pages": [{"url": "https://example.com/"}]},
        ),
        Finding(
            id="content.opening-hours-consistency",
            area="Local presence",
            title="Cross-page opening-hours consistency",
            status=Status.attention,
            severity="high",
            summary="1 conflicting opening-hours comparison was observed.",
            recommendation="Confirm authoritative business hours.",
            evidence={
                "conflicts": [
                    {
                        "first_url": "https://example.com/contact",
                        "second_url": "https://example.com/location",
                    }
                ]
            },
        ),
        Finding(
            id="email.spf",
            area="Trust and content quality",
            title="SPF policy",
            status=Status.attention,
            severity="medium",
            summary="Expected exactly one SPF policy; found 0.",
            recommendation="Publish exactly one SPF record.",
            evidence={"spf_records": []},
        ),
        Finding(
            id="ai.gptbot",
            area="AI discoverability",
            title="GPTBot access",
            status=Status.attention,
            severity="medium",
            summary="GPTBot access is blocked by robots.txt.",
            recommendation="Review robots.txt.",
            evidence={"disallow_all": True},
        ),
    ]
    assessment_id = TenantHistoryStore(root).save(
        identity,
        project_id,
        Assessment.build("https://example.com", findings, generated_at=NOW),
    )
    TenantAssessmentApprovalStore(root).approve(identity, project_id, assessment_id)
    captured: dict[str, str] = {}

    def fake_render_pdf(report_html: str, *, target: str) -> PdfDocument:
        captured["html"] = report_html
        captured["target"] = target
        return PdfDocument(b"%PDF-test", "informe.pdf")

    monkeypatch.setattr(tenant_report_api, "render_pdf", fake_render_pdf)
    response = _client(root, identity).get(
        f"/api/tenant/projects/{project_id}/assessments/{assessment_id}/report.pdf"
    )

    assert response.status_code == 200
    report = captured["html"]
    for expected in (
        '<html lang="es">',
        "Resumen ejecutivo",
        "Título de documento multipágina",
        "Etiquetas de formulario detectables",
        "Recursos activos inseguros",
        "Coherencia de horarios entre páginas",
        "Política SPF",
        "Acceso de GPTBot",
        "Páginas afectadas",
        "requiere atención",
    ):
        assert expected in report
    for source_text in (
        "1 of 3 crawled HTML pages need attention.",
        "1 crawled pages contain form controls without a detectable label.",
        "1 crawled pages reference active HTTP subresources.",
        "Expected exactly one SPF policy; found 0.",
        "GPTBot access is blocked by robots.txt.",
    ):
        assert source_text not in report
    assert captured["target"] == "https://example.com/"


def test_second_assessment_report_and_pdf_include_saved_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "tenants"
    identity = _identity("7" * 24, TenantRole.analyst)
    profile_id = TenantProfileStore(root).save(
        identity,
        ReportProfile(organisation_name="Tenant Agency"),
    )
    project_id = TenantProjectStore(root).save(
        identity,
        ClientProject.build(
            name="Recurring project",
            target_url="https://example.com",
            profile_id=profile_id,
        ),
    )
    history = TenantHistoryStore(root)
    first_id = history.save(
        identity,
        project_id,
        Assessment.build(
            "https://example.com",
            [
                Finding(
                    id="security.hsts",
                    area="Security posture",
                    title="Enable HSTS",
                    status=Status.attention,
                    severity="medium",
                    summary="HSTS is missing.",
                )
            ],
            generated_at=datetime(2026, 7, 25, tzinfo=UTC),
        ),
    )
    second_id = history.save(
        identity,
        project_id,
        Assessment.build(
            "https://example.com",
            [],
            generated_at=NOW,
        ),
    )
    approvals = TenantAssessmentApprovalStore(root)
    approvals.approve(identity, project_id, first_id)
    approvals.approve(identity, project_id, second_id)
    captured: dict[str, str] = {}

    def fake_render_pdf(report_html: str, *, target: str) -> PdfDocument:
        captured["html"] = report_html
        return PdfDocument(b"%PDF-test", "progress.pdf")

    monkeypatch.setattr(tenant_report_api, "render_pdf", fake_render_pdf)
    client = _client(root, identity)
    first = client.get(
        f"/api/tenant/projects/{project_id}/assessments/{first_id}/report"
    )
    second = client.get(
        f"/api/tenant/projects/{project_id}/assessments/{second_id}/report"
    )
    pdf = client.get(
        f"/api/tenant/projects/{project_id}/assessments/{second_id}/report.pdf"
    )

    assert first.status_code == 200
    assert "Progress since previous assessment" not in first.text
    assert second.status_code == 200
    assert "Progress since previous assessment" in second.text
    assert "Resolved findings</span><strong>1" in second.text
    assert pdf.status_code == 200
    assert "Progress since previous assessment" in captured["html"]
    assert "Resolved findings</span><strong>1" in captured["html"]


def test_production_free_plan_blocks_pdf_and_export_outputs(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    identity = _identity("8" * 24, TenantRole.analyst)
    project_id, assessment_id = _default_sources(root, identity)
    WorkspaceStore(root / identity.tenant_id / "workspace").save(
        WorkspaceConfig(plan=PlanName.free)
    )
    client = _client(root, identity, production=True)
    base = f"/api/tenant/projects/{project_id}/assessments/{assessment_id}"

    pdf = client.get(f"{base}/report.pdf")
    export = client.get(f"{base}/export")

    assert pdf.status_code == 429
    assert export.status_code == 429


def test_production_agency_plan_records_pdf_and_export_usage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "tenants"
    identity = _identity("9" * 24, TenantRole.analyst)
    project_id, assessment_id = _default_sources(root, identity)
    policy = TenantWorkspacePolicy(root)
    WorkspaceStore(root / identity.tenant_id / "workspace").save(
        WorkspaceConfig(plan=PlanName.agency)
    )

    monkeypatch.setattr(
        tenant_report_api,
        "render_pdf",
        lambda _html, *, target: PdfDocument(b"%PDF-test", "report.pdf"),
    )
    client = _client(root, identity, production=True)
    base = f"/api/tenant/projects/{project_id}/assessments/{assessment_id}"

    pdf = client.get(f"{base}/report.pdf")
    export = client.get(f"{base}/export")

    assert pdf.status_code == 200
    assert export.status_code == 200
    totals = policy.usage_ledger(identity).totals(
        usage_period(policy.load(identity))
    )
    assert totals[UsageKind.pdf] == 1
    assert totals[UsageKind.export] == 1


def test_production_runtime_middleware_does_not_double_count_pdf_usage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "tenants"
    identity = _identity("c" * 24, TenantRole.analyst)
    project_id, assessment_id = _default_sources(root, identity)
    WorkspaceStore(root / identity.tenant_id / "workspace").save(
        WorkspaceConfig(plan=PlanName.agency)
    )
    monkeypatch.setattr(
        tenant_report_api,
        "render_pdf",
        lambda _html, *, target: PdfDocument(b"%PDF-test", "report.pdf"),
    )
    client = _client(
        root,
        identity,
        production=True,
        commercial_middleware=True,
    )

    response = client.get(
        f"/api/tenant/projects/{project_id}/assessments/{assessment_id}/report.pdf"
    )

    assert response.status_code == 200
    policy = TenantWorkspacePolicy(root)
    totals = policy.usage_ledger(identity).totals(
        usage_period(policy.load(identity), now=NOW)
    )
    assert totals[UsageKind.pdf] == 1
