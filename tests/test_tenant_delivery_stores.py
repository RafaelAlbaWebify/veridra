from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from veridra.email_delivery import EmailAttempt, EmailKind, EmailStatus
from veridra.identity_bootstrap import BOOTSTRAP_CONFIRMATION, SQLiteIdentityBootstrap
from veridra.lead_delivery import DeliveryStatus, LeadDeliveryAttempt
from veridra.lead_form_tenant_binding import SQLiteLeadFormTenantBindingStore
from veridra.lead_store import LeadFormConfig, LeadFormStore
from veridra.tenant_bound_lead_capture import _attempt_stores
from veridra.tenant_delivery_stores import TenantDeliveryStoreError, TenantDeliveryStores

NOW = datetime(2026, 7, 25, 19, 0, tzinfo=UTC)


def _request(app: FastAPI) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/embed/audit/test",
            "headers": [],
            "app": app,
        }
    )


def _webhook_attempt(lead_id: str, form_id: str) -> LeadDeliveryAttempt:
    return LeadDeliveryAttempt(
        lead_id=lead_id,
        form_id=form_id,
        webhook_url="https://example.com/hook",
        attempted_at=NOW,
        status=DeliveryStatus.delivered,
        attempt_number=1,
        status_code=204,
        payload_sha256="a" * 64,
    )


def _email_attempt(lead_id: str) -> EmailAttempt:
    return EmailAttempt(
        kind=EmailKind.lead_notification,
        recipient="owner@example.com",
        attempted_at=NOW,
        status=EmailStatus.delivered,
        subject="New lead",
        message_sha256="b" * 64,
        attempt_number=1,
        related_id=lead_id,
        assessment_id="c" * 24,
    )


def test_attempts_with_same_related_id_are_isolated_by_tenant(tmp_path: Path) -> None:
    stores = TenantDeliveryStores(tmp_path / "tenants")
    first_tenant = "1" * 24
    second_tenant = "2" * 24
    lead_id = "3" * 24
    form_id = "4" * 24

    stores.webhook_attempts(first_tenant).save(_webhook_attempt(lead_id, form_id))
    stores.webhook_attempts(second_tenant).save(_webhook_attempt(lead_id, form_id))
    stores.email_attempts(first_tenant).save(_email_attempt(lead_id))
    stores.email_attempts(second_tenant).save(_email_attempt(lead_id))

    assert len(stores.webhook_attempts(first_tenant).list_for_lead(lead_id)) == 1
    assert len(stores.webhook_attempts(second_tenant).list_for_lead(lead_id)) == 1
    assert len(stores.email_attempts(first_tenant).list_for_related(lead_id)) == 1
    assert len(stores.email_attempts(second_tenant).list_for_related(lead_id)) == 1
    assert (tmp_path / "tenants" / first_tenant / "lead-deliveries").exists()
    assert (tmp_path / "tenants" / second_tenant / "email-deliveries").exists()


def test_invalid_tenant_id_is_rejected_before_path_construction(tmp_path: Path) -> None:
    stores = TenantDeliveryStores(tmp_path / "tenants")

    with pytest.raises(TenantDeliveryStoreError):
        stores.webhook_attempts("../other")
    with pytest.raises(TenantDeliveryStoreError):
        stores.email_attempts("z" * 24)


def test_bound_form_selects_tenant_attempt_stores(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "data"
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(data_root))
    database = tmp_path / "identity.sqlite3"
    owner = SQLiteIdentityBootstrap(database).create_first_owner(
        tenant_slug="customer-one",
        tenant_name="Customer one",
        owner_email="owner@example.com",
        owner_name="Owner",
        password="owner-correct-horse-battery",
        confirmation=BOOTSTRAP_CONFIRMATION,
        created_at=NOW,
    )
    form_id = LeadFormStore().save(
        LeadFormConfig(
            organisation_label="Customer one",
            consent_text="I agree to be contacted.",
        )
    )
    SQLiteLeadFormTenantBindingStore(database).bind(
        form_id=form_id,
        tenant_id=owner.tenant_id,
        created_by_user_id=owner.user_id,
        created_at=NOW,
    )
    app = FastAPI()
    app.state.veridra_identity_database = database
    app.state.veridra_tenant_data_root = data_root / "tenants"

    webhook_store, email_store = _attempt_stores(_request(app), form_id)

    assert webhook_store is not None
    assert email_store is not None
    assert webhook_store.directory == data_root / "tenants" / owner.tenant_id / "lead-deliveries"
    assert email_store.directory == data_root / "tenants" / owner.tenant_id / "email-deliveries"
    assert not (data_root / "leads" / "deliveries").exists()
    assert not (data_root / "email-deliveries").exists()


def test_unbound_form_keeps_legacy_delivery_defaults(tmp_path: Path) -> None:
    app = FastAPI()
    app.state.veridra_identity_database = tmp_path / "missing.sqlite3"
    app.state.veridra_tenant_data_root = tmp_path / "tenants"

    webhook_store, email_store = _attempt_stores(_request(app), "f" * 24)

    assert webhook_store is None
    assert email_store is None
