from __future__ import annotations

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from veridra.runtime_config import RuntimeEnvironment
from veridra.security_headers import SecurityHeadersMiddleware


def _client(environment: RuntimeEnvironment) -> TestClient:
    app = FastAPI()

    @app.get("/normal")
    def normal() -> dict[str, str]:
        return {"ok": "yes"}

    market = "/agency/prospects/discover/market/" + ("a" * 32)

    @app.get(market)
    def market_page() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get(market + "/map-view")
    def market_frame() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/embed/example")
    def embed() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/billing")
    def billing() -> dict[str, str]:
        return {"ok": "yes"}

    @app.post("/billing/checkout/solo")
    def billing_checkout() -> Response:
        from fastapi.responses import RedirectResponse

        return RedirectResponse("https://checkout.stripe.com/c/pay/test", status_code=303)

    @app.get("/stricter")
    def stricter() -> dict[str, str]:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            {"ok": "yes"},
            headers={"Referrer-Policy": "no-referrer"},
        )  # type: ignore[return-value]

    app.add_middleware(SecurityHeadersMiddleware, environment=environment)
    return TestClient(app)


def _assert_strict_sources(csp: str) -> None:
    assert "default-src 'none'" in csp
    assert "script-src 'none'" in csp
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "img-src 'self' data:" in csp
    assert "font-src 'self'" in csp
    assert "connect-src 'self'" in csp
    assert "form-action 'self'" in csp
    assert "frame-src 'none'" in csp
    assert "object-src 'none'" in csp
    assert "base-uri 'self'" in csp


def test_normal_response_gets_safe_global_headers() -> None:
    response = _client(RuntimeEnvironment.development).get("/normal")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    assert response.headers["x-frame-options"] == "DENY"
    csp = response.headers["content-security-policy"]
    _assert_strict_sources(csp)
    assert "frame-ancestors 'none'" in csp
    assert "strict-transport-security" not in response.headers


def test_embed_surface_remains_frameable_but_keeps_safe_headers() -> None:
    response = _client(RuntimeEnvironment.production).get("/embed/example")

    assert "x-frame-options" not in response.headers
    csp = response.headers["content-security-policy"]
    _assert_strict_sources(csp)
    assert "frame-ancestors" not in csp
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


def test_billing_csp_allows_only_required_stripe_form_destinations() -> None:
    client = _client(RuntimeEnvironment.production)

    page = client.get("/billing")
    checkout = client.post("/billing/checkout/solo", follow_redirects=False)

    for response in (page, checkout):
        csp = response.headers["content-security-policy"]
        assert (
            "form-action 'self' https://checkout.stripe.com https://billing.stripe.com"
            in csp
        )
        assert "https://stripe.com" not in csp

    normal_csp = client.get("/normal").headers["content-security-policy"]
    assert "form-action 'self';" in normal_csp
    assert "checkout.stripe.com" not in normal_csp
    assert "billing.stripe.com" not in normal_csp


def test_market_map_can_be_iframed_only_from_same_origin() -> None:
    client = _client(RuntimeEnvironment.operator)
    market = "/agency/prospects/discover/market/" + ("a" * 32)
    parent = client.get(market)
    frame = client.get(market + "/map-view")
    assert parent.status_code == 200
    assert frame.status_code == 200
    assert "frame-src 'self'" in parent.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in parent.headers["content-security-policy"]
    assert parent.headers["x-frame-options"] == "DENY"
    assert frame.headers["x-frame-options"] == "SAMEORIGIN"
    assert "frame-ancestors 'self'" in frame.headers["content-security-policy"]
    for path in ("/normal", market + "/map-view**", market + "/map-script"):
        response = client.get(path)
        assert response.headers["x-frame-options"] == "DENY"
        assert "frame-src 'none'" in response.headers["content-security-policy"]


def test_market_page_allows_only_same_origin_script_for_selection() -> None:
    client = _client(RuntimeEnvironment.operator)
    market = "/agency/prospects/discover/market/" + ("a" * 32)
    parent = client.get(market)
    assert "script-src 'self'" in parent.headers["content-security-policy"]
    assert "frame-src 'self'" in parent.headers["content-security-policy"]
    assert "script-src 'none'" in client.get("/normal").headers["content-security-policy"]
    assert "script-src 'none'" in (
        client.get("/agency/prospects/discover").headers["content-security-policy"]
    )
    assert "script-src 'none'" in (
        client.get(market + "/map-script").headers["content-security-policy"]
    )
