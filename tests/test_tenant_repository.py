from __future__ import annotations

from datetime import UTC, datetime

import pytest

from veridra.identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantCapability,
    TenantObjectRef,
    TenantRole,
)
from veridra.tenant_repository import (
    InMemoryTenantRepository,
    TenantRecord,
    TenantRepositoryError,
    TenantScopedRepository,
)

NOW = datetime(2026, 7, 24, 12, 30, tzinfo=UTC)
TENANT_A = "a" * 24
TENANT_B = "b" * 24


def _identity(tenant_id: str, role: TenantRole = TenantRole.owner) -> RequestIdentity:
    return RequestIdentity(
        user_id="c" * 24,
        tenant_id=tenant_id,
        membership_role=role,
        session_id="s" * 24,
        authenticated_at=NOW,
    )


def _record(tenant_id: str, object_id: str) -> TenantRecord:
    return TenantRecord(
        tenant_id=tenant_id,
        object_type="project",
        object_id=object_id,
        payload={"name": f"Project {object_id}"},
    )


def _contract(repository: TenantScopedRepository) -> TenantScopedRepository:
    return repository


def test_repository_contract_requires_tenant_qualified_references() -> None:
    repository = _contract(InMemoryTenantRepository([_record(TENANT_A, "shared-id")]))
    identity = _identity(TENANT_A)

    record = repository.load(
        identity,
        TenantObjectRef(
            tenant_id=TENANT_A,
            object_type="project",
            object_id="shared-id",
        ),
    )

    assert record.tenant_id == TENANT_A
    assert record.object_id == "shared-id"


def test_cross_tenant_load_is_rejected_before_existence_is_disclosed() -> None:
    repository = InMemoryTenantRepository([_record(TENANT_B, "secret")])

    with pytest.raises(IdentityBoundaryError, match="Cross-tenant"):
        repository.load(
            _identity(TENANT_A),
            TenantObjectRef(
                tenant_id=TENANT_B,
                object_type="project",
                object_id="secret",
            ),
        )


def test_same_object_id_isolated_between_tenants() -> None:
    repository = InMemoryTenantRepository(
        [
            _record(TENANT_A, "shared-id"),
            _record(TENANT_B, "shared-id"),
        ]
    )

    first = repository.load(
        _identity(TENANT_A),
        TenantObjectRef(
            tenant_id=TENANT_A,
            object_type="project",
            object_id="shared-id",
        ),
    )
    second = repository.load(
        _identity(TENANT_B),
        TenantObjectRef(
            tenant_id=TENANT_B,
            object_type="project",
            object_id="shared-id",
        ),
    )

    assert first.tenant_id != second.tenant_id


def test_list_only_returns_current_tenant_records() -> None:
    repository = InMemoryTenantRepository(
        [
            _record(TENANT_A, "one"),
            _record(TENANT_A, "two"),
            _record(TENANT_B, "hidden"),
        ]
    )

    records = repository.list_for_tenant(_identity(TENANT_A), "project")

    assert [record.object_id for record in records] == ["one", "two"]
    assert all(record.tenant_id == TENANT_A for record in records)


def test_save_and_delete_require_capability_and_scope() -> None:
    repository = InMemoryTenantRepository()
    viewer = _identity(TENANT_A, TenantRole.viewer)
    owner = _identity(TENANT_A, TenantRole.owner)
    record = _record(TENANT_A, "new")

    with pytest.raises(IdentityBoundaryError, match="capability"):
        repository.save(viewer, record, TenantCapability.manage_projects)

    repository.save(owner, record, TenantCapability.manage_projects)
    assert repository.load(owner, record.reference) == record

    with pytest.raises(IdentityBoundaryError, match="Cross-tenant"):
        repository.delete(
            owner,
            TenantObjectRef(
                tenant_id=TENANT_B,
                object_type="project",
                object_id="new",
            ),
            TenantCapability.manage_projects,
        )

    repository.delete(owner, record.reference, TenantCapability.manage_projects)
    with pytest.raises(TenantRepositoryError, match="not found"):
        repository.load(owner, record.reference)
