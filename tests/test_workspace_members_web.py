from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from veridra.workspace_members import AuditTrailStore, MemberStore
from veridra.workspace_members_web import router
from veridra.workspace_policy import PlanName, WorkspaceConfig, WorkspaceStore


def _client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    plan: PlanName = PlanName.agency,
) -> TestClient:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))
    WorkspaceStore().save(WorkspaceConfig(plan=plan))
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_first_member_must_be_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    response = client.post(
        "/members",
        data={
            "display_name": "Analyst",
            "email": "analyst@example.com",
            "role": "analyst",
            "active": "yes",
        },
    )
    assert response.status_code == 400
    assert MemberStore().list() == []


def test_create_edit_and_export_members(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    created = client.post(
        "/members",
        data={
            "display_name": "Rafael Alba",
            "email": "rafael@example.com",
            "role": "owner",
            "active": "yes",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303
    member = MemberStore().list()[0]

    updated = client.post(
        f"/members/{member.id}",
        data={
            "display_name": "Rafael Alba",
            "email": "rafael@example.com",
            "role": "administrator",
            "active": "yes",
        },
    )
    assert updated.status_code == 409

    csv_response = client.get("/members.csv")
    assert csv_response.status_code == 200
    assert "rafael@example.com" in csv_response.text
    assert "owner" in csv_response.text


def test_seat_limit_and_last_owner_protection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch, PlanName.free)
    first = client.post(
        "/members",
        data={
            "display_name": "Owner",
            "email": "owner@example.com",
            "role": "owner",
            "active": "yes",
        },
    )
    assert first.status_code == 200
    second = client.post(
        "/members",
        data={
            "display_name": "Viewer",
            "email": "viewer@example.com",
            "role": "viewer",
            "active": "yes",
        },
    )
    assert second.status_code == 429

    owner = MemberStore().list()[0]
    deleted = client.post(f"/members/{owner.id}/delete")
    assert deleted.status_code == 409


def test_member_actions_create_audit_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    client.post(
        "/members",
        data={
            "display_name": "Owner",
            "email": "owner@example.com",
            "role": "owner",
            "active": "yes",
        },
    )
    member = MemberStore().list()[0]
    client.post(
        "/members",
        data={
            "display_name": "Sales",
            "email": "sales@example.com",
            "role": "sales",
            "active": "yes",
        },
    )
    events = [event.action for _, event in AuditTrailStore().list()]
    assert events.count("member.created") == 2

    page = client.get("/members/audit")
    assert page.status_code == 200
    assert "unauthenticated local operator interface" in page.text
    assert member.id in page.text

    export = client.get("/members/audit.csv")
    assert export.status_code == 200
    assert "member.created" in export.text


def test_member_dashboard_states_identity_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    response = client.get("/members")
    assert response.status_code == 200
    assert "not login accounts" in response.text
    assert "Create first local owner" in response.text
