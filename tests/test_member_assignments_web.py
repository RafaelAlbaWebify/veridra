from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from veridra.lead_store import AuditLead, LeadStore
from veridra.member_assignments_web import router
from veridra.project_store import ClientProject, ProjectStore
from veridra.task_store import RemediationTask, TaskStore
from veridra.workspace_members import AuditTrailStore, MemberRole, MemberStore, WorkspaceMember
from veridra.workspace_policy import PlanName, WorkspaceConfig

IDENTIFIER = "a" * 24


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _member(tmp_path: Path, *, active: bool = True) -> WorkspaceMember:
    member = WorkspaceMember.build(
        display_name="Alex <Analyst>",
        email="alex@example.com",
        role=MemberRole.owner,
        active=active,
    )
    MemberStore().save(member, WorkspaceConfig(plan=PlanName.agency))
    return member


def _fixtures() -> tuple[str, str, str]:
    project_id = ProjectStore().save(
        ClientProject.build(
            name="Client <Project>",
            target_url="https://example.com",
            contact_label="Legacy contact",
        )
    )
    lead_id = LeadStore().save(
        AuditLead.model_validate(
            {
                "form_id": IDENTIFIER,
                "website": "https://example.com",
                "name": "Lead <Name>",
                "email": "lead@example.com",
                "consent_text": "Agreed",
                "consented_at": datetime.now(UTC),
                "assessment_id": IDENTIFIER,
                "assigned_owner": "Legacy lead owner",
            }
        )
    )
    task_id = TaskStore().save(
        RemediationTask(
            project_id=IDENTIFIER,
            finding_id="finding",
            title="Task <Title>",
            source_assessment_id=IDENTIFIER,
            owner_label="Legacy task owner",
        )
    )
    return project_id, lead_id, task_id


def test_dashboard_escapes_content_and_lists_legacy_assignments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))
    _member(tmp_path)
    _fixtures()

    response = _client().get("/assignments")

    assert response.status_code == 200
    assert "Client &lt;Project&gt;" in response.text
    assert "Lead &lt;Name&gt;" in response.text
    assert "Task &lt;Title&gt;" in response.text
    assert "Alex &lt;Analyst&gt;" in response.text
    assert "Legacy contact" in response.text


def test_assignment_routes_persist_member_references_and_audit_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))
    member = _member(tmp_path)
    project_id, lead_id, task_id = _fixtures()
    client = _client()

    assert client.post(
        f"/assignments/projects/{project_id}",
        data={"member_id": member.id, "legacy_label": "Project fallback"},
        follow_redirects=False,
    ).status_code == 303
    assert client.post(
        f"/assignments/leads/{lead_id}",
        data={"member_id": member.id, "legacy_label": "Lead fallback"},
        follow_redirects=False,
    ).status_code == 303
    assert client.post(
        f"/assignments/tasks/{task_id}",
        data={"member_id": member.id, "legacy_label": "Task fallback"},
        follow_redirects=False,
    ).status_code == 303

    projects = [ProjectStore().load(entry.id) for entry in ProjectStore().list()]
    assert projects[0].contact_member_id == member.id
    assert projects[0].contact_label == "Project fallback"
    assert LeadStore().load_lead(lead_id).assigned_owner_member_id == member.id
    tasks = [task for _, task in TaskStore().list()]
    assert tasks[0].owner_member_id == member.id
    assert len(AuditTrailStore().list()) == 3


def test_assignment_rejects_missing_member_and_preserves_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))
    project_id, _, _ = _fixtures()

    response = _client().post(
        f"/assignments/projects/{project_id}",
        data={"member_id": "f" * 24, "legacy_label": "Changed"},
    )

    assert response.status_code == 400
    project = ProjectStore().load(project_id)
    assert project.contact_member_id is None
    assert project.contact_label == "Legacy contact"


def test_assignment_can_clear_member_reference_and_keep_legacy_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))
    member = _member(tmp_path)
    _, lead_id, _ = _fixtures()
    store = LeadStore()
    lead = store.load_lead(lead_id)
    store.replace(
        lead_id,
        AuditLead.model_validate(
            lead.model_copy(update={"assigned_owner_member_id": member.id})
        ),
    )

    response = _client().post(
        f"/assignments/leads/{lead_id}",
        data={"member_id": "", "legacy_label": "Manual owner"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    updated = store.load_lead(lead_id)
    assert updated.assigned_owner_member_id is None
    assert updated.assigned_owner == "Manual owner"
