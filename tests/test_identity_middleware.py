from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from veridra.identity_middleware import TrustedIdentityAdapter, VerifiedIdentityMiddleware
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.request_security import require_request_identity

NOW = datetime(2026, 7, 24, 13, 0, tzinfo=UTC)


def _identity() -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id="b" * 24,
        membership_role=TenantRole.owner,
        session_id="s" * 24,
        authenticated_at=NOW,
    )


class StaticAdapter:
    def __init__(self, identity: RequestIdentity | None) -> None:
        self.identity = identity

    async def resolve(self, request: object) -> RequestIdentity | None:
        del request
        return self.identity


def _app(adapter: TrustedIdentityAdapter) -> FastAPI:
    app = FastAPI()
    app.add_middleware(VerifiedIdentityMiddleware, adapter=adapter)

    @app.get("/protected")
    def protected(
        identity: Annotated[RequestIdentity, Depends(require_request_identity)],
    ) -> dict[str, str]:
        return {"tenant_id": identity.tenant_id}

    return app


def test_middleware_binds_identity_from_trusted_adapter() -> None:
    client = TestClient(_app(StaticAdapter(_identity())))

    response = client.get("/protected")

    assert response.status_code == 200
    assert response.json() == {"tenant_id": "b" * 24}


def test_middleware_leaves_request_anonymous_when_adapter_returns_none() -> None:
    client = TestClient(_app(StaticAdapter(None)))

    response = client.get("/protected")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication is required."}


def test_client_headers_cannot_create_identity_without_adapter_resolution() -> None:
    client = TestClient(_app(StaticAdapter(None)))

    response = client.get(
        "/protected",
        headers={
            "x-user-id": "a" * 24,
            "x-tenant-id": "b" * 24,
            "x-role": "owner",
        },
    )

    assert response.status_code == 401
