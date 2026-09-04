from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from httpx import Response as HTTPResponse

from veridra.agency_recurring_service_web import router
from veridra.customer_store import CustomerRecord, CustomerSourceType
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_store import ClientProject, ProjectStore
from veridra.recurring_service import RecurringServiceStatus
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_customer_store import TenantCustomerStore
from veridra.tenant_recurring_service_store import TenantRecurringServiceStore

ORIGIN = "http://testserver"
NOW = datetime(2026, 9, 4, 10, 0, tzinfo=UTC)
OWNER = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.owner,
    session_id="recurring-owner-session-01",
    authenticated_at=NOW,
)


def _client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, Path, str, str]:
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
            name="Synthetic recurring service",
            target_url="https://example.com",
            client_label="Synthetic client",
        )
    )
    customer = CustomerRecord(
        business_name="Synthetic recurring customer",
        source_type=CustomerSourceType.prospect,
        source_id="b" * 24,
        project_ids=(project_id,),
    )
    customer_id = TenantCustomerStore(root).upsert(OWNER, customer)
    return TestClient(app), root, project_id, customer_id


def _post(
    client: TestClient,
    path: str,
    data: dict[str, str] | None = None,
) -> HTTPResponse:
    return cast(
        HTTPResponse,
        client.post(
            path,
            headers={"Origin": ORIGIN},
            data=data or {},
            follow_redirects=False,
        ),
    )


def test_recurring_full_operator_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, root, project_id, customer_id = _client(tmp_path, monkeypatch)
    base = f"/agency/projects/{project_id}/recurring"

    page = client.get(base)
    assert page.status_code == 200
    assert "Configure recurring plan" in page.text
    assert "Synthetic recurring customer" in page.text

    configured = _post(
        client,
        f"{base}/configure",
        {
            "scope": "Monthly website health review\nMonitoring review",
            "deliverables": "Monthly monitoring review\nMonthly client summary",
            "exclusions": "New page builds\nPaid media",
            "fee": "99.00",
            "currency": "EUR",
            "billing_cadence": "monthly",
            "cadence_description": "Monthly review and report",
            "response_time": "Review within two business days",
            "escalation_expectations": "Availability evidence surfaced first",
            "effective_from": "2026-09-05",
        },
    )
    assert configured.status_code == 303
    assert _post(client, f"{base}/offer").status_code == 303

    activated = _post(
        client,
        f"{base}/accept",
        {
            "acceptance_reference": "Synthetic customer accepts recurring plan v1.",
            "start_date": "2026-09-05",
            "next_billing_date": "2026-10-05",
            "renewal_date": "2026-10-05",
            "minimum_term_months": "0",
            "renewal_behavior": "manual",
            "monitoring_cadence": "Monthly",
            "report_cadence": "Monthly",
        },
    )
    assert activated.status_code == 303

    delivered = _post(
        client,
        f"{base}/deliverable",
        {
            "deliverable": "Monthly monitoring review",
            "reference": "Synthetic monitoring/report evidence 2026-09.",
        },
    )
    assert delivered.status_code == 303

    paused = _post(
        client,
        f"{base}/pause",
        {"reference": "Synthetic customer-requested temporary pause."},
    )
    assert paused.status_code == 303
    record = TenantRecurringServiceStore(root).load_or_empty(
        OWNER, project_id, customer_id
    )
    assert record.status is RecurringServiceStatus.paused
    assert _post(
        client,
        f"{base}/resume",
        {"reference": "Synthetic customer requests service resume."},
    ).status_code == 303

    failed = _post(
        client,
        f"{base}/payment",
        {
            "invoice_reference": "INV-RECUR-002",
            "payment_state": "failed",
            "payment_reference": "Provider attempt failed synthetic ref",
            "next_billing_date": "2026-10-05",
        },
    )
    assert failed.status_code == 303
    record = TenantRecurringServiceStore(root).load_or_empty(
        OWNER, project_id, customer_id
    )
    assert record.status is RecurringServiceStatus.payment_blocked

    recovered = _post(
        client,
        f"{base}/payment",
        {
            "invoice_reference": "INV-RECUR-002",
            "payment_state": "paid",
            "payment_reference": "PAY-RECUR-002",
            "next_billing_date": "2026-11-05",
        },
    )
    assert recovered.status_code == 303

    renewed = _post(
        client,
        f"{base}/renew",
        {
            "scope": (
                "Monthly website health review\nMonitoring review\n"
                "Quarterly conversion-path review"
            ),
            "deliverables": "Monthly monitoring review\nMonthly client summary",
            "exclusions": "New page builds\nPaid media",
            "fee": "129.00",
            "currency": "EUR",
            "billing_cadence": "monthly",
            "cadence_description": "Monthly review and quarterly conversion-path review",
            "response_time": "Review within two business days",
            "escalation_expectations": "Availability evidence surfaced first",
            "effective_from": "2026-10-05",
            "renewal_reference": "Synthetic customer approval of recurring v2.",
        },
    )
    assert renewed.status_code == 303
    record = TenantRecurringServiceStore(root).load_or_empty(
        OWNER, project_id, customer_id
    )
    assert record.current_version == 2
    assert record.active_version is not None
    assert str(record.active_version.fee) == "129.00"

    notice = _post(
        client,
        f"{base}/cancel-notice",
        {
            "notice_date": "2026-10-20",
            "effective_date": "2026-11-05",
            "reference": "Synthetic cancellation notice.",
        },
    )
    assert notice.status_code == 303
    cancelled = _post(
        client,
        f"{base}/cancel-complete",
        {
            "effective_date": "2026-11-05",
            "exit_handoff_reference": (
                "Synthetic ownership/access exit checklist completed."
            ),
        },
    )
    assert cancelled.status_code == 303
    record = TenantRecurringServiceStore(root).load_or_empty(
        OWNER, project_id, customer_id
    )
    assert record.status is RecurringServiceStatus.cancelled
    assert record.exit_handoff_reference
    assert record.completed_deliverables == ("Monthly monitoring review",)
    assert [item.version for item in record.versions] == [1, 2]

    final_page = client.get(base)
    assert "Recurring service is cancelled" in final_page.text
    index = client.get("/agency/recurring-services")
    assert index.status_code == 200
    assert "Recurring revenue" in index.text
    assert "Synthetic recurring customer" in index.text
    assert "Cancelled" in index.text


def test_recurring_page_exposes_existing_change_request_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _root, project_id, _customer_id = _client(tmp_path, monkeypatch)
    base = f"/agency/projects/{project_id}/recurring"
    assert _post(
        client,
        f"{base}/configure",
        {
            "scope": "Monitoring review",
            "deliverables": "Monthly summary",
            "fee": "99.00",
            "currency": "EUR",
            "billing_cadence": "monthly",
            "cadence_description": "Monthly",
        },
    ).status_code == 303
    assert _post(client, f"{base}/offer").status_code == 303
    assert _post(
        client,
        f"{base}/accept",
        {
            "acceptance_reference": "Synthetic acceptance.",
            "start_date": "2026-09-05",
            "next_billing_date": "2026-10-05",
            "minimum_term_months": "0",
            "renewal_behavior": "manual",
            "monitoring_cadence": "Monthly",
            "report_cadence": "Monthly",
        },
    ).status_code == 303
    page = client.get(base)
    assert "/agency/prospects/" + "b" * 24 + "/deal/change-requests" in page.text
    assert "Out-of-scope / overage Change Request" in page.text
