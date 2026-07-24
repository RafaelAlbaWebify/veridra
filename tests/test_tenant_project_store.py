from __future__ import annotations

from datetime import UTC, datetime

import pytest

from veridra.identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantObjectRef,
    TenantRole,
)
from veridra.project_store import ClientProject
from veridra.tenant_project_store import TenantProjectStore, TenantProjectStoreError

NOW = datetime(2026, 7, 24, 16, 0, tzinfo=UTC)


def _identity(tenant: str, role: TenantRole = TenantRole.owner) -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id=tenant,
        membership_role=role,
        session_id="session-tenant-project-store",
        authenticated_at=NOW,
    )


def _project(name: str) -> ClientProject:
    return ClientProject.build(name=name, target_url="https://example.com")


def test_same_project_content_is_isolated_by_tenant_directory(tmp_path) -> None:
    store = TenantProjectStore(tmp_path)
    tenant_a = _identity("b" * 24)
    tenant_b = _identity("c" * 24)

    project_id_a = store.save(tenant_a, _project("Shared"))
    project_id_b = store.save(tenant_b, _project("Shared"))

    assert project_id_a == project_id_b
    assert store.load(tenant_a, store.ref(tenant_a, project_id_a)).name == "Shared"
    assert store.load(tenant_b, store.ref(tenant_b, project_id_b)).name == "Shared"
    assert (tmp_path / tenant_a.tenant_id / "projects" / f"{project_id_a}.json").exists()
    assert (tmp_path / tenant_b.tenant_id / "projects" / f"{project_id_b}.json").exists()


def test_cross_tenant_reference_is_rejected_before_lookup(tmp_path) -> None:
    store = TenantProjectStore(tmp_path)
    tenant_a = _identity("b" * 24)
    tenant_b = _identity("c" * 24)
    project_id = store.save(tenant_b, _project("Private"))

    target = TenantObjectRef(
        tenant_id=tenant_b.tenant_id,
        object_type="project",
        object_id=project_id,
    )

    with pytest.raises(IdentityBoundaryError, match="Cross-tenant"):
        store.load(tenant_a, target)


def test_viewer_can_list_and_load_but_cannot_write(tmp_path) -> None:
    store = TenantProjectStore(tmp_path)
    owner = _identity("b" * 24)
    viewer = _identity("b" * 24, TenantRole.viewer)
    project_id = store.save(owner, _project("Readable"))

    assert [entry.id for entry in store.list(viewer)] == [project_id]
    assert store.load(viewer, store.ref(viewer, project_id)).name == "Readable"

    with pytest.raises(IdentityBoundaryError, match="manage_projects"):
        store.save(viewer, _project("Forbidden"))


def test_replace_and_delete_require_tenant_scoped_project_reference(tmp_path) -> None:
    store = TenantProjectStore(tmp_path)
    identity = _identity("b" * 24)
    project_id = store.save(identity, _project("Original"))
    target = store.ref(identity, project_id)

    replacement_id = store.replace(identity, target, _project("Replacement"))
    assert replacement_id != project_id
    assert store.load(identity, store.ref(identity, replacement_id)).name == "Replacement"

    store.delete(identity, store.ref(identity, replacement_id))
    with pytest.raises(TenantProjectStoreError, match="not found"):
        store.load(identity, store.ref(identity, replacement_id))


def test_non_project_reference_is_rejected(tmp_path) -> None:
    store = TenantProjectStore(tmp_path)
    identity = _identity("b" * 24)
    target = TenantObjectRef(
        tenant_id=identity.tenant_id,
        object_type="report",
        object_id="r-1",
    )

    with pytest.raises(TenantProjectStoreError, match="not a project"):
        store.load(identity, target)
