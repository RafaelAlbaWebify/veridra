from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from veridra.core import Assessment, Finding, Status
from veridra.identity_tenancy import IdentityBoundaryError, RequestIdentity, TenantRole
from veridra.project_store import ClientProject
from veridra.tenant_history_store import TenantHistoryStore, TenantHistoryStoreError
from veridra.tenant_project_store import TenantProjectStore

NOW = datetime(2026, 7, 25, 23, 0, tzinfo=UTC)


def _identity(tenant_id: str, role: TenantRole = TenantRole.analyst) -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id=tenant_id,
        membership_role=role,
        session_id="b" * 24,
        authenticated_at=NOW,
    )


def _assessment(title: str = "Missing HSTS") -> Assessment:
    return Assessment.build(
        "https://example.com",
        [
            Finding(
                id="security.hsts",
                area="Security posture",
                title=title,
                status=Status.attention,
                severity="medium",
                summary="HSTS is missing.",
                recommendation="Enable HSTS.",
            )
        ],
        generated_at=NOW,
    )


def _project(root: Path, identity: RequestIdentity) -> str:
    return TenantProjectStore(root).save(
        identity,
        ClientProject.build(name="Tenant project", target_url="https://example.com"),
    )


def test_same_assessment_id_is_isolated_between_tenants(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    first = _identity("1" * 24)
    second = _identity("2" * 24)
    first_project = _project(root, first)
    second_project = _project(root, second)
    assessment = _assessment()
    store = TenantHistoryStore(root)

    first_id = store.save(first, first_project, assessment)
    second_id = store.save(second, second_project, assessment)

    assert first_project == second_project
    assert first_id == second_id
    assert store.load(first, store.ref(first, first_project, first_id)) == assessment
    assert store.load(second, store.ref(second, second_project, second_id)) == assessment
    assert (
        root
        / first.tenant_id
        / "projects"
        / first_project
        / "assessments"
        / f"{first_id}.json"
    ).exists()
    assert not (tmp_path / "history").exists()


def test_viewer_reads_but_sales_cannot_save_assessments(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    analyst = _identity("3" * 24)
    viewer = _identity("3" * 24, TenantRole.viewer)
    sales = _identity("3" * 24, TenantRole.sales)
    project_id = _project(root, analyst)
    store = TenantHistoryStore(root)
    assessment_id = store.save(analyst, project_id, _assessment())

    assert store.list(viewer, project_id)[0].id == assessment_id
    with pytest.raises(IdentityBoundaryError):
        store.save(sales, project_id, _assessment("Different"))


def test_cross_tenant_reference_is_rejected_before_lookup(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    first = _identity("4" * 24)
    second = _identity("5" * 24)
    project_id = _project(root, first)
    store = TenantHistoryStore(root)
    assessment_id = store.save(first, project_id, _assessment())

    with pytest.raises(IdentityBoundaryError):
        store.load(second, store.ref(first, project_id, assessment_id))


def test_missing_or_foreign_project_creates_no_history(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    first = _identity("6" * 24)
    second = _identity("7" * 24)
    foreign_project = _project(root, second)
    store = TenantHistoryStore(root)

    with pytest.raises(TenantHistoryStoreError):
        store.save(first, foreign_project, _assessment())

    assert not (root / first.tenant_id / "projects").exists()


def test_compare_is_limited_to_one_tenant_project(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    identity = _identity("8" * 24)
    project_id = _project(root, identity)
    store = TenantHistoryStore(root)
    before_id = store.save(identity, project_id, _assessment("Old title"))
    after_id = store.save(identity, project_id, _assessment("New title"))

    comparison = store.compare(identity, project_id, before_id, after_id)

    assert comparison.changed == ("security.hsts",)
