from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from veridra.application_identity import configure_identity_middleware
from veridra.identity_middleware import TrustedIdentityAdapter, VerifiedIdentityMiddleware
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.same_origin import SameOriginConfigurationError, TrustedSameOriginPolicy

NOW = datetime(2026, 7, 26, 6, 0, tzinfo=UTC)
TRUSTED_ORIGIN = "https://app.veridra.example"


class StaticAdapter:
    def __init__(self, identity: RequestIdentity | None) -> None:
        self.identity = identity

    async def resolve(self, request: object) -> RequestIdentity | None:
        del request
        return self.identity


def _identity() -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id="b" * 24,
        membership_role=TenantRole.owner,
        session_id="c" * 24,
        authenticated_at=NOW,
    )


def _app(
    adapter: TrustedIdentityAdapter,
    *,
    trusted_origin: str = TRUSTED_ORIGIN,
) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        VerifiedIdentityMiddleware,
        adapter=adapter,
        same_origin_policy=TrustedSameOriginPolicy(trusted_origin),
    )

    @app.get("/api/tenant/projects")
    def safe_read() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/tenant/projects")
    def protected_write() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/embed/audit/form-id")
    def public_embed() -> dict[str, bool]:
        return {"ok": True}

    return app


def test_authenticated_same_origin_and_referer_fallback_succeed() -> None:
    client = TestClient(_app(StaticAdapter(_identity())))

    origin_response = client.post(
        "/api/tenant/projects",
        headers={"Origin": TRUSTED_ORIGIN},
    )
    referer_response = client.post(
        "/api/tenant/projects",
        headers={"Referer": f"{TRUSTED_ORIGIN}/projects/one"},
    )

    assert origin_response.status_code == 200
    assert referer_response.status_code == 200


def test_authenticated_cross_origin_missing_and_null_origin_are_rejected_for_production() -> None:
    client = TestClient(_app(StaticAdapter(_identity())))

    cross_origin = client.post(
        "/api/tenant/projects",
        headers={"Origin": "https://attacker.example"},
    )
    missing = client.post("/api/tenant/projects")
    null_origin = client.post(
        "/api/tenant/projects",
        headers={"Origin": "null"},
    )

    assert cross_origin.status_code == 403
    assert missing.status_code == 403
    assert null_origin.status_code == 403
    assert cross_origin.json() == {
        "detail": "Authenticated request origin is not permitted."
    }


def test_originless_exact_loopback_request_is_allowed() -> None:
    origin = "http://127.0.0.1:8010"
    client = TestClient(
        _app(StaticAdapter(_identity()), trusted_origin=origin),
        base_url=origin,
    )

    response = client.post("/api/tenant/projects")

    assert response.status_code == 200


def test_null_origin_exact_loopback_request_is_allowed() -> None:
    origin = "http://127.0.0.1:8010"
    client = TestClient(
        _app(StaticAdapter(_identity()), trusted_origin=origin),
        base_url=origin,
    )

    response = client.post(
        "/api/tenant/projects",
        headers={"Origin": "null"},
    )

    assert response.status_code == 200


def test_null_origin_loopback_request_with_wrong_host_is_rejected() -> None:
    trusted = "http://127.0.0.1:8010"
    client = TestClient(
        _app(StaticAdapter(_identity()), trusted_origin=trusted),
        base_url="http://localhost:8010",
    )

    response = client.post(
        "/api/tenant/projects",
        headers={"Origin": "null"},
    )

    assert response.status_code == 403


def test_originless_loopback_request_with_wrong_host_is_rejected() -> None:
    trusted = "http://127.0.0.1:8010"
    client = TestClient(
        _app(StaticAdapter(_identity()), trusted_origin=trusted),
        base_url="http://localhost:8010",
    )

    response = client.post("/api/tenant/projects")

    assert response.status_code == 403


def test_forwarded_headers_cannot_redefine_trusted_origin() -> None:
    client = TestClient(_app(StaticAdapter(_identity())))

    response = client.post(
        "/api/tenant/projects",
        headers={
            "Origin": "https://attacker.example",
            "X-Forwarded-Host": "app.veridra.example",
            "X-Forwarded-Proto": "https",
        },
    )

    assert response.status_code == 403


def test_safe_requests_public_embed_and_anonymous_mutations_are_unaffected() -> None:
    authenticated = TestClient(_app(StaticAdapter(_identity())))
    anonymous = TestClient(_app(StaticAdapter(None)))

    assert authenticated.get("/api/tenant/projects").status_code == 200
    assert authenticated.post("/embed/audit/form-id").status_code == 200
    assert anonymous.post("/api/tenant/projects").status_code == 200


def test_cookie_authentication_requires_trusted_origin_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERIDRA_IDENTITY_DB", str(tmp_path / "identity.sqlite3"))
    monkeypatch.delenv("VERIDRA_TRUSTED_ORIGIN", raising=False)

    with pytest.raises(SameOriginConfigurationError, match="TRUSTED_ORIGIN"):
        configure_identity_middleware(FastAPI())


def test_cookie_authentication_accepts_normalized_trusted_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERIDRA_IDENTITY_DB", str(tmp_path / "identity.sqlite3"))
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", f"{TRUSTED_ORIGIN}/")

    app = FastAPI()

    assert configure_identity_middleware(app)
