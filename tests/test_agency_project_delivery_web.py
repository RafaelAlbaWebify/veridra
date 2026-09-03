from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from httpx import Response as HTTPResponse

from veridra.agency_project_customer_web import router
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_delivery import (
    CustomerReviewState,
    DeliveryMilestone,
    RecurringServiceDecision,
)
from veridra.project_store import ClientProject, ProjectStore
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_project_delivery_store import TenantProjectDeliveryStore

ORIGIN = "http://testserver"
NOW = datetime(2026, 9, 3, 15, 0, tzinfo=UTC)
OWNER = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.owner,
    session_id="delivery-owner",
    authenticated_at=NOW,
)


def _client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, Path, str]:
    root = tmp_path / "tenants"
    app = FastAPI()
    app.state.veridra_tenant_data_root = root

    @app.middleware("http")
    async def identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        bind_verified_request_identity(request, OWNER)
        return await call_next(request)

    app.include_router(router)
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", ORIGIN)
    project_id = ProjectStore(root / OWNER.tenant_id / "projects").save(
        ClientProject.build(
            name="Synthetic delivery",
            target_url="https://example.com",
            client_label="Synthetic client",
        )
    )
    return TestClient(app), root, project_id


def _post(
    client: TestClient,
    path: str,
    data: dict[str, str] | None = None,
) -> HTTPResponse:
    return client.post(
        path,
        headers={"Origin": ORIGIN},
        data=data or {},
        follow_redirects=False,
    )


def test_delivery_revision_acceptance_handoff_balance_and_closure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, root, project_id = _client(tmp_path, monkeypatch)
    base = f"/agency/projects/{project_id}/delivery"

    page = client.get(base)
    assert page.status_code == 200
    assert "Delivery setup" in page.text

    configured = _post(
        client,
        f"{base}/configure",
        {
            "deliverables": "Client report\nImplemented fixes\nVerification summary",
            "revision_policy": "One included revision against agreed scope.",
            "included_revisions": "1",
            "acceptance_criteria": "Agreed deliverables complete and verified.",
            "final_balance_required": "yes",
        },
    )
    assert configured.status_code == 303
    assert _post(client, f"{base}/ready").status_code == 303

    requested = _post(
        client,
        f"{base}/changes-requested",
        {"reference": "Customer email requests one in-scope copy revision."},
    )
    assert requested.status_code == 303
    record = TenantProjectDeliveryStore(root).load_or_empty(OWNER, project_id)
    assert record.milestone is DeliveryMilestone.revision_in_progress
    assert record.revisions_used == 1

    completed = _post(
        client,
        f"{base}/revision-completed",
        {"reference": "Revision 1 completed and verification rerun."},
    )
    assert completed.status_code == 303

    unresponsive = _post(
        client,
        f"{base}/unresponsive",
        {"reference": "Follow-up sent after review deadline; no reply."},
    )
    assert unresponsive.status_code == 303
    record = TenantProjectDeliveryStore(root).load_or_empty(OWNER, project_id)
    assert record.review_state is CustomerReviewState.unresponsive
    assert record.milestone is DeliveryMilestone.ready_for_review

    paused_page = client.get(base)
    assert "project remains open" in paused_page.text
    assert _post(client, f"{base}/resume-review").status_code == 303

    accepted = _post(
        client,
        f"{base}/accept",
        {"reference": "Customer accepted final delivery by email."},
    )
    assert accepted.status_code == 303
    assert _post(client, f"{base}/start-handoff").status_code == 303

    handed_off = _post(
        client,
        f"{base}/handoff-complete",
        {
            "backups": "yes",
            "access": "yes",
            "documentation": "yes",
            "reference": "Backup retained; access transferred; handoff guide acknowledged.",
        },
    )
    assert handed_off.status_code == 303

    closed = _post(
        client,
        f"{base}/close",
        {
            "completion_summary": "Agreed sprint delivered, revised, accepted and handed off.",
            "final_balance_evidence": (
                "Invoice INV-SYN-001 marked paid in synthetic billing evidence."
            ),
            "recurring_decision": "declined",
        },
    )
    assert closed.status_code == 303

    record = TenantProjectDeliveryStore(root).load_or_empty(OWNER, project_id)
    assert record.milestone is DeliveryMilestone.closed
    assert record.review_state is CustomerReviewState.accepted
    assert record.accepted_at is not None
    assert record.handoff_complete
    assert record.closed_at is not None
    assert record.recurring_decision is RecurringServiceDecision.declined
    assert [event.action for event in record.events] == [
        "delivery_setup_saved",
        "delivery_ready",
        "changes_requested",
        "revision_completed",
        "customer_unresponsive",
        "review_resumed",
        "customer_accepted",
        "handoff_started",
        "handoff_completed",
        "project_closed",
    ]

    final_page = client.get(base)
    assert "Project closed" in final_page.text
    assert "Open change request instead" in final_page.text


def test_revision_beyond_included_allowance_requires_change_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, root, project_id = _client(tmp_path, monkeypatch)
    base = f"/agency/projects/{project_id}/delivery"
    assert _post(
        client,
        f"{base}/configure",
        {
            "deliverables": "Client report",
            "revision_policy": "No included revisions; changes require approval.",
            "included_revisions": "0",
            "acceptance_criteria": "Report delivered and reviewed.",
        },
    ).status_code == 303
    assert _post(client, f"{base}/ready").status_code == 303

    response = _post(
        client,
        f"{base}/changes-requested",
        {"reference": "Customer requests additional work."},
    )
    assert response.status_code == 409
    assert "Change Request" in response.text

    record = TenantProjectDeliveryStore(root).load_or_empty(OWNER, project_id)
    assert record.revisions_used == 0
    assert record.review_state is CustomerReviewState.awaiting_review
    page = client.get(base)
    assert "Out-of-scope change request" in page.text
