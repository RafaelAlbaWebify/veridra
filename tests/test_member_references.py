from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from veridra.lead_store import AuditLead
from veridra.member_references import (
    member_reference_label,
    MemberReferenceError,
    require_active_member,
)
from veridra.project_store import ClientProject
from veridra.task_store import RemediationTask
from veridra.workspace_members import MemberRole, MemberStore, WorkspaceMember
from veridra.workspace_policy import PlanName, WorkspaceConfig


IDENTIFIER = "a" * 24


def _member_store(tmp_path: Path) -> tuple[MemberStore, WorkspaceMember]:
    store = MemberStore(tmp_path / "members")
    member = WorkspaceMember.build(
        display_name="Alex Analyst",
        email="alex@example.com",
        role=MemberRole.owner,
    )
    store.save(member, WorkspaceConfig(plan=PlanName.agency))
    return store, member


def test_legacy_models_load_without_member_references() -> None:
    project = ClientProject.model_validate(
        {"name": "Legacy", "target_url": "https://example.com"}
    )
    lead = AuditLead.model_validate(
        {
            "form_id": IDENTIFIER,
            "website": "https://example.com",
            "name": "Legacy lead",
            "email": "lead@example.com",
            "consent_text": "Agreed",
            "consented_at": datetime.now(UTC),
            "assessment_id": IDENTIFIER,
            "assigned_owner": "Legacy owner",
        }
    )
    task = RemediationTask.model_validate(
        {
            "project_id": IDENTIFIER,
            "finding_id": "finding",
            "title": "Legacy task",
            "owner_label": "Legacy technician",
            "source_assessment_id": IDENTIFIER,
        }
    )

    assert project.contact_member_id is None
    assert project.contact_label is None
    assert lead.assigned_owner_member_id is None
    assert lead.assigned_owner == "Legacy owner"
    assert task.owner_member_id is None
    assert task.owner_label == "Legacy technician"


def test_active_member_reference_resolves_to_display_name(tmp_path: Path) -> None:
    store, member = _member_store(tmp_path)

    assert require_active_member(member.id, store=store) == member.id
    assert member_reference_label(member.id, "Legacy owner", store=store) == "Alex Analyst"


def test_missing_member_reference_preserves_legacy_label(tmp_path: Path) -> None:
    store = MemberStore(tmp_path / "members")

    assert member_reference_label(IDENTIFIER, "Legacy owner", store=store) == "Legacy owner"
    with pytest.raises(MemberReferenceError, match="not found"):
        require_active_member(IDENTIFIER, store=store)


def test_inactive_member_reference_preserves_legacy_label(tmp_path: Path) -> None:
    store, member = _member_store(tmp_path)
    inactive = member.model_copy(
        update={"active": False, "updated_at": datetime.now(UTC)}
    )
    member_path = store.directory / f"{member.id}.json"
    member_path.write_text(inactive.model_dump_json(), encoding="utf-8")

    assert member_reference_label(member.id, "Legacy owner", store=store) == "Legacy owner"
    with pytest.raises(MemberReferenceError, match="inactive"):
        require_active_member(member.id, store=store)


def test_member_reference_identifiers_are_structurally_validated() -> None:
    with pytest.raises(ValueError):
        ClientProject.build(
            name="Invalid",
            target_url="https://example.com",
            contact_member_id="not-an-id",
        )
    with pytest.raises(ValueError):
        AuditLead.model_validate(
            {
                "form_id": IDENTIFIER,
                "website": "https://example.com",
                "name": "Lead",
                "email": "lead@example.com",
                "consent_text": "Agreed",
                "consented_at": datetime.now(UTC),
                "assessment_id": IDENTIFIER,
                "assigned_owner_member_id": "not-an-id",
            }
        )
    with pytest.raises(ValueError):
        RemediationTask.model_validate(
            {
                "project_id": IDENTIFIER,
                "finding_id": "finding",
                "title": "Task",
                "source_assessment_id": IDENTIFIER,
                "owner_member_id": "not-an-id",
            }
        )
