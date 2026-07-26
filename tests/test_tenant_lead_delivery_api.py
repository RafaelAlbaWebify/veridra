from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from pydantic import HttpUrl
from starlette.requests import Request

from veridra.email_delivery import EmailAttempt, EmailKind, EmailStatus
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.lead_delivery import DeliveryStatus, LeadDeliveryAttempt
from veridra.lead_store import AuditLead
from veridra.tenant_delivery_stores import TenantDeliveryStores
from veridra.tenant_lead_api import list_delivery_attempts
from veridra.tenant_lead_store import TenantLeadStore

NOW = datetime(2026, 7, 25, 20, 0, tzinfo=UTC)


def _identity(tenant_id: str) -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id=tenant_id,
        membership_role=TenantRole.viewer,
        session_id="b" * 24,
        authenticated_at=NOW,
    )


def _request(root: Path) -> Request:
    app = FastAPI()
    app.state.veridra_tenant_data_root = root
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/tenant/leads/test/delivery-attempts",
            "headers": [],
            "app": app,
        }
    )


def _lead() -> AuditLead:
    return AuditLead(
        form_id="c" * 24,
        website=HttpUrl("https://example.com"),
        name="Prospect",
        email="prospect@example.com",
        consent_text="I agree to be contacted.",
        consented_at=NOW,
        assessment_id="d" * 24,
    )


def test_delivery_attempt_endpoint_reads_only_authenticated_tenant(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    first = _identity("1" * 24)
    second = _identity("2" * 24)
    lead_store = TenantLeadStore(root)
    lead_id = lead_store.save_bound_public_capture(tenant_id=first.tenant_id, lead=_lead())
    attempts = TenantDeliveryStores(root)
    attempts.webhook_attempts(first.tenant_id).save(
        LeadDeliveryAttempt(
            lead_id=lead_id,
            form_id="c" * 24,
            webhook_url="https://example.com/hook",
            attempted_at=NOW,
            status=DeliveryStatus.delivered,
            attempt_number=1,
            status_code=204,
            payload_sha256="e" * 64,
        )
    )
    attempts.email_attempts(first.tenant_id).save(
        EmailAttempt(
            kind=EmailKind.lead_notification,
            recipient="owner@example.com",
            attempted_at=NOW,
            status=EmailStatus.delivered,
            subject="New lead",
            message_sha256="f" * 64,
            attempt_number=1,
            related_id=lead_id,
            assessment_id="d" * 24,
        )
    )

    result = list_delivery_attempts(lead_id, _request(root), first)

    assert len(result["webhook"]) == 1
    assert len(result["email"]) == 1
    assert result["webhook"][0]["lead_id"] == lead_id
    assert result["email"][0]["related_id"] == lead_id
    with pytest.raises(HTTPException) as error:
        list_delivery_attempts(lead_id, _request(root), second)
    assert error.value.status_code == 404


def test_missing_lead_hides_orphan_attempt_records(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    identity = _identity("3" * 24)
    lead_id = "4" * 24
    TenantDeliveryStores(root).email_attempts(identity.tenant_id).save(
        EmailAttempt(
            kind=EmailKind.lead_notification,
            recipient="owner@example.com",
            attempted_at=NOW,
            status=EmailStatus.failed,
            subject="New lead",
            message_sha256="5" * 64,
            attempt_number=1,
            related_id=lead_id,
            error="Delivery failed.",
        )
    )

    with pytest.raises(HTTPException) as error:
        list_delivery_attempts(lead_id, _request(root), identity)

    assert error.value.status_code == 404
