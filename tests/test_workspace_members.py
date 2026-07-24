from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from veridra.workspace_members import (
    AuditEvent,
    AuditTrailStore,
    Capability,
    MemberRole,
    MemberStore,
    MemberStoreError,
    WorkspaceMember,
)
from veridra.workspace_policy import PlanName, WorkspaceConfig


def _member(
    name: str,
    email: str,
    role: MemberRole,
    *,
    active: bool = True,
) -> WorkspaceMember:
    return WorkspaceMember.build(
        display_name=name,
        email=email,
        role=role,
        active=active,
        now=datetime(2026, 7, 23, 12, 0, tzinfo=UTC),
    )


def test_role_capabilities_are_deterministic() -> None:
    owner = _member("Owner", "owner@example.com", MemberRole.owner)
    sales = _member("Sales", "sales@example.com", MemberRole.sales)
    viewer = _member("Viewer", "viewer@example.com", MemberRole.viewer)

    assert owner.can(Capability.manage_members)
    assert sales.can(Capability.manage_leads)
    assert not sales.can(Capability.manage_workspace)
    assert viewer.can(Capability.view_data)
    assert not viewer.can(Capability.manage_reports)


def test_member_id_is_stable_for_identity_fields() -> None:
    first = _member("Rafael Alba", "Rafael@Example.com", MemberRole.owner)
    second = _member("Rafael Alba", "rafael@example.com", MemberRole.analyst)
    assert first.id == second.id


def test_free_plan_allows_only_one_active_member(tmp_path: Path) -> None:
    store = MemberStore(tmp_path)
    workspace = WorkspaceConfig(plan=PlanName.free)
    store.save(_member("Owner", "owner@example.com", MemberRole.owner), workspace)

    with pytest.raises(MemberStoreError, match="seat allowance"):
        store.save(_member("Viewer", "viewer@example.com", MemberRole.viewer), workspace)


def test_agency_plan_allows_multiple_members(tmp_path: Path) -> None:
    store = MemberStore(tmp_path)
    workspace = WorkspaceConfig(plan=PlanName.agency)
    owner = _member("Owner", "owner@example.com", MemberRole.owner)
    analyst = _member("Analyst", "analyst@example.com", MemberRole.analyst)

    store.save(owner, workspace)
    store.save(analyst, workspace)

    assert [member.id for member in store.list()] == [analyst.id, owner.id]


def test_last_active_owner_cannot_be_disabled(tmp_path: Path) -> None:
    store = MemberStore(tmp_path)
    workspace = WorkspaceConfig(plan=PlanName.agency)
    owner = _member("Owner", "owner@example.com", MemberRole.owner)
    store.save(owner, workspace)

    disabled = owner.model_copy(
        update={
            "active": False,
            "updated_at": datetime(2026, 7, 24, tzinfo=UTC),
        }
    )
    with pytest.raises(MemberStoreError, match="active workspace owner"):
        store.save(disabled, workspace)


def test_last_active_owner_cannot_be_deleted(tmp_path: Path) -> None:
    store = MemberStore(tmp_path)
    workspace = WorkspaceConfig(plan=PlanName.agency)
    owner = _member("Owner", "owner@example.com", MemberRole.owner)
    store.save(owner, workspace)

    with pytest.raises(MemberStoreError, match="active workspace owner"):
        store.delete(owner.id)


def test_member_files_are_isolated_when_malformed(tmp_path: Path) -> None:
    store = MemberStore(tmp_path)
    workspace = WorkspaceConfig(plan=PlanName.agency)
    owner = _member("Owner", "owner@example.com", MemberRole.owner)
    store.save(owner, workspace)
    (tmp_path / "broken.json").write_text("not-json", encoding="utf-8")

    assert store.list() == [owner]


def test_audit_trail_is_append_only_and_deterministic(tmp_path: Path) -> None:
    store = AuditTrailStore(tmp_path)
    event = AuditEvent(
        action="member.created",
        occurred_at=datetime(2026, 7, 23, 12, 0, tzinfo=UTC),
        actor_member_id="a" * 24,
        subject_type="workspace_member",
        subject_id="b" * 24,
        detail="Created analyst member.",
    )

    first = store.record(event)
    second = store.record(event)

    assert first == second
    assert store.list() == [(first, event)]
