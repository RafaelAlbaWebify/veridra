from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from veridra.runtime_config import RuntimeEnvironment
from veridra.security_headers import SecurityHeadersMiddleware


def _client(environment: RuntimeEnvironment) -> TestClient:
    app = FastAPI()

    @app.get("/normal")
    def normal() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/embed/example")
    def embed() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/stricter")
    def stricter() -> dict[str, str]:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            {"ok": "yes"},
            headers={"Referrer-Policy": "no-referrer"},
        )  # type: ignore[return-value]

    app.add_middleware(SecurityHeadersMiddleware, environment=environment)
    return TestClient(app)


def test_normal_response_gets_safe_global_headers() -> None:
    response = _client(RuntimeEnvironment.development).get("/normal")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["content-security-policy"] == (
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    )
    assert "strict-transport-security" not in response.headers


def test_embed_surface_remains_frameable_but_keeps_safe_headers() -> None:
    response = _client(RuntimeEnvironment.production).get("/embed/example")

    assert "x-frame-options" not in response.headers
    assert response.headers["content-security-policy"] == "object-src 'none'; base-uri 'self'"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["strict-transport-security"] == (
        "max-age=31536000; includeSubDomains"
    )


def test_existing_stricter_route_header_is_preserved() -> None:
    response = _client(RuntimeEnvironment.production).get("/stricter")

    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-frame-options"] == "DENY"


def test_production_adds_hsts() -> None:
    response = _client(RuntimeEnvironment.production).get("/normal")

    assert response.headers["strict-transport-security"] == (
        "max-age=31536000; includeSubDomains"
    )
