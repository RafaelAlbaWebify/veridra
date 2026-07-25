from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from veridra.identity_tenancy import (
    RequestIdentity,
    TenantAuthorizationError,
    TenantObjectRef,
    TenantRole,
)
from veridra.lead_store import LeadFormConfig, LeadFormStore, LeadStoreError
from veridra.tenant_lead_form_store import TenantLeadFormStore, TenantLeadFormStoreError

NOW = datetime(2026, 7, 25, 18, 0, tzinfo=UTC)


def _identity(tenant_id: str, role: TenantRole) -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id=tenant_id,
        membership_role=role,
        session_id="b" * 24,
        authenticated_at=NOW,
    )


def _form(label: str) -> LeadFormConfig:
    return LeadFormConfig(
        organisation_label=label,
        consent_text="I agree to be contacted.",
    )


def test_same_form_id_is_isolated_between_tenants(tmp_path: Path) -> None:
    store = TenantLeadFormStore(tmp_path / "tenants")
    first = _identity("1" * 24, TenantRole.owner)
    second = _identity("2" * 24, TenantRole.owner)
    form = _form("Shared configuration")

    first_id = store.save(first, form)
    second_id = store.save(second, form)

    assert first_id == second_id
    assert store.load(first, store.ref(first, first_id)) == form
    assert store.load(second, store.ref(second, second_id)) == form
    assert (
        tmp_path / "tenants" / first.tenant_id / "lead-forms" / f"{first_id}.json"
    ).exists()
    assert (
        tmp_path / "tenants" / second.tenant_id / "lead-forms" / f"{second_id}.json"
    ).exists()


def test_cross_tenant_and_wrong_type_references_fail(tmp_path: Path) -> None:
    store = TenantLeadFormStore(tmp_path / "tenants")
    owner = _identity("3" * 24, TenantRole.owner)
    other = _identity("4" * 24, TenantRole.owner)
    form_id = store.save(owner, _form("Owner form"))

    with pytest.raises(TenantAuthorizationError):
        store.load(other, TenantObjectRef(owner.tenant_id, "lead-form", form_id))
    with pytest.raises(TenantLeadFormStoreError):
        store.load(owner, TenantObjectRef(owner.tenant_id, "lead", form_id))


def test_viewer_reads_but_cannot_mutate_and_sales_can_manage(tmp_path: Path) -> None:
    store = TenantLeadFormStore(tmp_path / "tenants")
    tenant_id = "5" * 24
    sales = _identity(tenant_id, TenantRole.sales)
    viewer = _identity(tenant_id, TenantRole.viewer)
    form_id = store.save(sales, _form("Sales form"))

    assert store.list(viewer)[0][0] == form_id
    assert store.load(viewer, store.ref(viewer, form_id)).organisation_label == "Sales form"
    with pytest.raises(TenantAuthorizationError):
        store.save(viewer, _form("Forbidden"))


def test_tenant_forms_do_not_fall_back_to_legacy_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "data"
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(data_root))
    tenant_store = TenantLeadFormStore(data_root / "tenants")
    owner = _identity("6" * 24, TenantRole.owner)
    form_id = tenant_store.save(owner, _form("Tenant only"))

    with pytest.raises(LeadStoreError):
        LeadFormStore().load_form(form_id)
    loaded = tenant_store.load_public(tenant_id=owner.tenant_id, form_id=form_id)
    assert loaded.organisation_label == "Tenant only"
