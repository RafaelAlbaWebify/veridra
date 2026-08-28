from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi import Response as FastAPIResponse
from fastapi.testclient import TestClient
from pydantic import HttpUrl

from veridra.agency_commercial_dashboard_web import router as commercial_router
from veridra.commercial_dashboard import build_commercial_snapshot
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.lead_store import AuditLead, LeadStatus
from veridra.project_store import ClientProject
from veridra.prospect import Prospect, ProspectStatus
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_project_store import TenantProjectStore

NOW = datetime(2026, 8, 28, 10, 0, tzinfo=UTC)


def _identity(tenant_char: str = "b") -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id=tenant_char * 24,
        membership_role=TenantRole.owner,
        session_id="commercial-dashboard-session",
        authenticated_at=NOW,
    )


def _lead(status: LeadStatus, follow_up: datetime | None = None) -> AuditLead:
    return AuditLead(
        form_id="c" * 24,
        website=HttpUrl("https://example.com"),
        name="Example Lead",
        email="lead@example.com",
        consent_text="I agree",
        consented_at=NOW,
        assessment_id="d" * 24,
        status=status,
        next_follow_up_at=follow_up,
        currency="EUR",
    )


def _prospect(status: ProspectStatus, follow_up: datetime | None = None) -> Prospect:
    payload: dict[str, object] = {
        "business_name": f"Prospect {status.value}",
        "status": status,
        "next_follow_up_at": follow_up,
    }
    if status is ProspectStatus.lost:
        payload["commercial_loss_reason"] = "NO_RESPONSE"
    if status is ProspectStatus.unsuitable:
        payload["rejection_reason"] = "NO_CONTACT_ROUTE"
    return Prospect.model_validate(payload)


def test_due_followups_exclude_future_and_terminal_records() -> None:
    prospects = [
        _prospect(ProspectStatus.contacted, NOW - timedelta(minutes=1)),
        _prospect(ProspectStatus.proposal, NOW + timedelta(days=1)),
        _prospect(ProspectStatus.customer, NOW - timedelta(days=1)),
        _prospect(ProspectStatus.lost, NOW - timedelta(days=1)),
    ]
    leads = [
        _lead(LeadStatus.contacted, NOW),
        _lead(LeadStatus.qualified, NOW + timedelta(hours=1)),
        _lead(LeadStatus.won, NOW - timedelta(days=1)),
        _lead(LeadStatus.lost, NOW - timedelta(days=1)),
    ]

    snapshot = build_commercial_snapshot(prospects, leads, [], as_of=NOW)

    assert snapshot.prospect_due_followups == 1
    assert snapshot.lead_due_followups == 1
    assert snapshot.due_followups == 2


def test_conversion_kpis_and_project_count_are_deterministic() -> None:
    prospects = [
        _prospect(ProspectStatus.contacted),
        _prospect(ProspectStatus.responded),
        _prospect(ProspectStatus.customer),
        _prospect(ProspectStatus.lost),
        _prospect(ProspectStatus.needs_review),
    ]
    leads = [
        _lead(LeadStatus.won),
        _lead(LeadStatus.won),
        _lead(LeadStatus.lost),
        _lead(LeadStatus.qualified),
    ]

    snapshot = build_commercial_snapshot(
        prospects,
        leads,
        [],
        projects=[object(), object(), object()],
        as_of=NOW,
    )

    assert snapshot.project_count == 3
    assert snapshot.outbound_conversion_rate == Decimal("25.00")
    assert snapshot.inbound_win_rate == Decimal("66.67")


def test_conversion_kpis_are_safe_with_zero_denominators() -> None:
    snapshot = build_commercial_snapshot([], [], [], as_of=NOW)

    assert snapshot.outbound_conversion_rate == Decimal("0.00")
    assert snapshot.inbound_win_rate == Decimal("0.00")
    assert snapshot.project_count == 0


def test_dashboard_counts_only_current_tenant_projects(tmp_path: Path) -> None:
    identity = _identity("b")
    other_identity = _identity("e")
    project_store = TenantProjectStore(tmp_path)
    project_store.save(
        identity,
        ClientProject.build(
            name="Current tenant project",
            target_url="https://current.example",
        ),
    )
    project_store.save(
        other_identity,
        ClientProject.build(
            name="Other tenant project",
            target_url="https://other.example",
        ),
    )

    app = FastAPI()
    app.state.veridra_tenant_data_root = tmp_path

    @app.middleware("http")
    async def bind_identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[FastAPIResponse]],
    ) -> FastAPIResponse:
        bind_verified_request_identity(request, identity)
        return await call_next(request)

    app.include_router(commercial_router)
    response = TestClient(app).get("/agency/commercial")

    assert response.status_code == 200
    assert "<span class='muted'>Client projects</span><div class='metric'>1</div>" in response.text
    assert "Due follow-ups" in response.text
    assert "Outbound customer conversion" in response.text
    assert "Inbound win rate" in response.text
