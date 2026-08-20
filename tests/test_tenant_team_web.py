from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra.identity_bootstrap import BOOTSTRAP_CONFIRMATION, SQLiteIdentityBootstrap
from veridra.identity_email_delivery import TenantInvitationDelivery
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.request_security import bind_verified_request_identity
from veridra.sqlite_identity_store import SQLiteIdentityRecordStore
from veridra.tenant_invitations import SQLiteTenantInvitationService
from veridra.tenant_team_web import router
from veridra.workspace_policy import PlanName, WorkspaceConfig, WorkspaceStore

NOW = datetime(2026, 8, 20, 13, 0, tzinfo=UTC)


def _client(tmp_path: Path) -> tuple[TestClient, Path, Path, RequestIdentity]:
    database = tmp_path / "identity.sqlite3"
    root = tmp_path / "tenants"
    created = SQLiteIdentityBootstrap(database).create_first_owner(
        tenant_slug="customer-one",
        tenant_name="Customer one",
        owner_email="owner@example.com",
        owner_name="Owner Name",
        password="owner-correct-horse-battery",
        confirmation=BOOTSTRAP_CONFIRMATION,
        created_at=NOW,
    )
    owner = RequestIdentity(
        user_id=created.user_id,
        tenant_id=created.tenant_id,
        membership_role=TenantRole.owner,
        session_id="team-owner-session-00001",
        authenticated_at=NOW,
    )
    viewer = RequestIdentity(
        user_id="2" * 24,
        tenant_id=created.tenant_id,
        membership_role=TenantRole.viewer,
        session_id="team-viewer-session-0001",
        authenticated_at=NOW,
    )
    WorkspaceStore(root / created.tenant_id / "workspace").save(
        WorkspaceConfig(plan=PlanName.agency)
    )
    app = FastAPI()
    app.state.veridra_identity_store = SQLiteIdentityRecordStore(database)
    app.state.veridra_tenant_data_root = root

    @app.middleware("http")
    async def identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        role = request.headers.get("x-test-role")
        if role == "owner":
            bind_verified_request_identity(request, owner)
        elif role == "viewer":
            bind_verified_request_identity(request, viewer)
        return await call_next(request)

    app.include_router(router)
    return TestClient(app), database, root, owner


def test_team_page_is_tenant_native_and_permission_bound(tmp_path: Path) -> None:
    client, _, _, _ = _client(tmp_path)

    anonymous = client.get("/workspace/members")
    viewer = client.get("/workspace/members", headers={"x-test-role": "viewer"})
    owner = client.get("/workspace/members", headers={"x-test-role": "owner"})

    assert anonymous.status_code == 401
    assert viewer.status_code == 403
    assert owner.status_code == 200
    assert "href='/workspace/members' aria-current='page'" in owner.text
    assert "Owner Name" in owner.text
    assert "owner@example.com" in owner.text
    assert "1 / 10 active seats" in owner.text
    assert "real authenticated tenant memberships" in owner.text
    assert "href='/members'" not in owner.text


def test_team_invitation_create_resend_and_cancel_without_email_uses_manual_fallback(
    tmp_path: Path,
) -> None:
    client, database, root, owner = _client(tmp_path)
    headers = {"x-test-role": "owner"}

    created = client.post(
        "/workspace/members/invite",
        headers=headers,
        data={"email": "analyst@example.com", "role": "analyst"},
    )

    assert created.status_code == 200
    assert "Invitation ready for analyst@example.com" in created.text
    assert "Transactional email is not configured" in created.text
    service = SQLiteTenantInvitationService(database, root)
    active = service.list_active(tenant_id=owner.tenant_id, now=NOW)
    assert len(active) == 1
    invitation_id = active[0].id

    listed = client.get("/workspace/members", headers=headers)
    assert "analyst@example.com" in listed.text
    assert "Resend invitation" in listed.text
    assert "Cancel" in listed.text

    resent = client.post(
        f"/workspace/members/invitations/{invitation_id}/resend",
        headers=headers,
    )
    assert resent.status_code == 200
    assert "Invitation ready for analyst@example.com" in resent.text
    replacement = service.list_active(tenant_id=owner.tenant_id, now=NOW)
    assert len(replacement) == 1
    assert replacement[0].id != invitation_id

    cancelled = client.post(
        f"/workspace/members/invitations/{replacement[0].id}/cancel",
        headers=headers,
        follow_redirects=False,
    )
    assert cancelled.status_code == 303
    assert cancelled.headers["location"] == "/workspace/members"
    assert service.list_active(tenant_id=owner.tenant_id, now=NOW) == ()


def test_team_invitation_uses_email_adapter_without_exposing_token(tmp_path: Path) -> None:
    client, _, _, _ = _client(tmp_path)
    deliveries: list[TenantInvitationDelivery] = []

    def deliver(delivery: TenantInvitationDelivery) -> bool:
        deliveries.append(delivery)
        return True

    app = cast(FastAPI, client.app)
    app.state.veridra_tenant_invitation_delivery = deliver
    response = client.post(
        "/workspace/members/invite",
        headers={"x-test-role": "owner"},
        data={"email": "analyst@example.com", "role": "analyst"},
    )

    assert response.status_code == 200
    assert "Invitation email sent to analyst@example.com" in response.text
    assert len(deliveries) == 1
    assert deliveries[0].email == "analyst@example.com"
    assert deliveries[0].token not in response.text


def test_team_invitation_delivery_failure_keeps_active_invitation(tmp_path: Path) -> None:
    client, database, root, owner = _client(tmp_path)
    app = cast(FastAPI, client.app)
    app.state.veridra_tenant_invitation_delivery = lambda delivery: False

    response = client.post(
        "/workspace/members/invite",
        headers={"x-test-role": "owner"},
        data={"email": "analyst@example.com", "role": "analyst"},
    )

    assert response.status_code == 200
    assert "email delivery to analyst@example.com failed" in response.text
    active = SQLiteTenantInvitationService(database, root).list_active(
        tenant_id=owner.tenant_id,
        now=NOW,
    )
    assert len(active) == 1


def test_team_rejects_owner_invitation(tmp_path: Path) -> None:
    client, _, _, _ = _client(tmp_path)

    response = client.post(
        "/workspace/members/invite",
        headers={"x-test-role": "owner"},
        data={"email": "other@example.com", "role": "owner"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Owner invitations are not permitted."
