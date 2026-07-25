from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_store import ClientProject
from veridra.report_profiles import ReportProfile
from veridra.request_security import require_request_identity
from veridra.tenant_profile_store import TenantProfileStore
from veridra.tenant_project_api import build_tenant_project_router
from veridra.tenant_project_store import TenantProjectStore, TenantProjectStoreError

NOW = datetime(2026, 7, 25, 22, 0, tzinfo=UTC)


def _identity(tenant_id: str) -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id=tenant_id,
        membership_role=TenantRole.analyst,
        session_id="b" * 24,
        authenticated_at=NOW,
    )


def test_project_requires_profile_in_same_tenant(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    first = _identity("1" * 24)
    second = _identity("2" * 24)
    profile_id = TenantProfileStore(root).save(
        second,
        ReportProfile(organisation_name="Other tenant"),
    )
    project = ClientProject.build(
        name="Tenant project",
        target_url="https://example.com",
        profile_id=profile_id,
    )

    with pytest.raises(TenantProjectStoreError):
        TenantProjectStore(root).save(first, project)

    assert not (root / first.tenant_id / "projects").exists()


def test_project_accepts_profile_in_current_tenant(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    identity = _identity("3" * 24)
    profile_id = TenantProfileStore(root).save(
        identity,
        ReportProfile(organisation_name="Current tenant"),
    )
    project = ClientProject.build(
        name="Tenant project",
        target_url="https://example.com",
        profile_id=profile_id,
    )

    project_id = TenantProjectStore(root).save(identity, project)

    assert TenantProjectStore(root).load(
        identity,
        TenantProjectStore(root).ref(identity, project_id),
    ) == project


def test_project_api_conceals_missing_profile(tmp_path: Path) -> None:
    identity = _identity("4" * 24)
    app = FastAPI()
    app.include_router(build_tenant_project_router(root=tmp_path / "tenants"))
    app.dependency_overrides[require_request_identity] = lambda: identity
    client = TestClient(app)

    response = client.post(
        "/api/tenant/projects",
        json={
            "name": "Tenant project",
            "target_url": "https://example.com",
            "profile_id": "f" * 24,
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Report profile not found."}
