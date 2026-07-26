from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from veridra.identity_middleware import VerifiedIdentityMiddleware
from veridra.identity_tenancy import (
    AccountStatus,
    AuthenticatedUser,
    AuthSession,
    SessionStatus,
    Tenant,
    TenantMembership,
    TenantRole,
    TenantStatus,
)
from veridra.request_security import require_request_identity
from veridra.session_identity_adapter import (
    IdentityRecordSet,
    ServerSideSessionIdentityAdapter,
)

NOW = datetime(2026, 7, 24, 14, 0, tzinfo=UTC)
TENANT_ID = "b" * 24
USER_ID = "a" * 24


class StaticExtractor:
    def __init__(self, credential: str | None) -> None:
        self.credential = credential

    async def extract(self, request: Request) -> str | None:
        del request
        return self.credential


class RecordingStore:
    def __init__(self, records: IdentityRecordSet | None) -> None:
        self.records = records
        self.credentials: list[str] = []

    async def load_by_credential(self, credential: str) -> IdentityRecordSet | None:
        self.credentials.append(credential)
        return self.records


def _records(
    *,
    tenant_status: TenantStatus = TenantStatus.active,
    session_status: SessionStatus = SessionStatus.active,
    membership_active: bool = True,
) -> IdentityRecordSet:
    return IdentityRecordSet(
        user=AuthenticatedUser(
            id=USER_ID,
            email="owner@example.com",
            display_name="Owner",
            status=AccountStatus.active,
            email_verified_at=NOW - timedelta(days=30),
            created_at=NOW - timedelta(days=60),
        ),
        tenant=Tenant(
            id=TENANT_ID,
            slug="example-tenant",
            display_name="Example Tenant",
            status=tenant_status,
            created_at=NOW - timedelta(days=60),
        ),
        membership=TenantMembership(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            role=TenantRole.owner,
            active=membership_active,
            created_at=NOW - timedelta(days=60),
        ),
        session=AuthSession(
            id="session-credential-record-001",
            user_id=USER_ID,
            status=session_status,
            issued_at=NOW - timedelta(minutes=10),
            expires_at=NOW + timedelta(hours=1),
            revoked_at=NOW - timedelta(minutes=1)
            if session_status == SessionStatus.revoked
            else None,
        ),
    )


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


@pytest.mark.asyncio
async def test_missing_credential_stays_anonymous_without_store_lookup() -> None:
    store = RecordingStore(_records())
    adapter = ServerSideSessionIdentityAdapter(
        extractor=StaticExtractor(None),
        store=store,
        clock=lambda: NOW,
    )

    assert await adapter.resolve(_request()) is None
    assert store.credentials == []


@pytest.mark.asyncio
async def test_adapter_rebuilds_identity_from_current_server_records() -> None:
    store = RecordingStore(_records())
    adapter = ServerSideSessionIdentityAdapter(
        extractor=StaticExtractor("opaque-session-value"),
        store=store,
        clock=lambda: NOW,
    )

    identity = await adapter.resolve(_request())

    assert identity is not None
    assert identity.user_id == USER_ID
    assert identity.tenant_id == TENANT_ID
    assert identity.membership_role == TenantRole.owner
    assert store.credentials == ["opaque-session-value"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("records"),
    [
        _records(tenant_status=TenantStatus.suspended),
        _records(session_status=SessionStatus.revoked),
        _records(membership_active=False),
    ],
)
async def test_invalid_current_records_fail_closed(records: IdentityRecordSet) -> None:
    adapter = ServerSideSessionIdentityAdapter(
        extractor=StaticExtractor("opaque-session-value"),
        store=RecordingStore(records),
        clock=lambda: NOW,
    )

    assert await adapter.resolve(_request()) is None


def test_adapter_integrates_with_verified_identity_middleware() -> None:
    app = FastAPI()
    adapter = ServerSideSessionIdentityAdapter(
        extractor=StaticExtractor("opaque-session-value"),
        store=RecordingStore(_records()),
        clock=lambda: NOW,
    )
    app.add_middleware(VerifiedIdentityMiddleware, adapter=adapter)

    @app.get("/protected")
    def protected(request: Request) -> dict[str, str]:
        identity = require_request_identity(request)
        return {"tenant_id": identity.tenant_id}

    response = TestClient(app).get(
        "/protected",
        headers={"x-user-id": "f" * 24, "x-tenant-id": "f" * 24, "x-role": "viewer"},
    )

    assert response.status_code == 200
    assert response.json() == {"tenant_id": TENANT_ID}
