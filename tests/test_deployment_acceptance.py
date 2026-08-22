from __future__ import annotations

import httpx
import pytest

from veridra.deployment_acceptance import (
    DeploymentCheckStatus,
    _pin_deployment_request,
    run_deployment_acceptance,
)

ORIGIN = "https://app.example.test"


def _headers() -> dict[str, str]:
    return {
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": (
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        ),
        "Cache-Control": "no-store",
    }


def _transport(
    *,
    ready: bool = True,
    hsts: bool = True,
    schema_hidden: bool = True,
    onboarding_hidden: bool = True,
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        headers = _headers()
        if not hsts:
            headers.pop("Strict-Transport-Security")
        if request.url.path == "/health/live":
            return httpx.Response(200, headers=headers, json={"status": "ok"})
        if request.url.path == "/health/ready":
            return httpx.Response(
                200 if ready else 503,
                headers=headers,
                json={"status": "ok" if ready else "not_ready"},
            )
        if request.url.path == "/signup":
            return httpx.Response(
                200,
                headers=headers,
                text="<h1>Create your Veridra agency workspace</h1>",
            )
        if request.url.path == "/onboarding":
            return httpx.Response(
                404 if onboarding_hidden else 200,
                headers=headers,
                text="Not found" if onboarding_hidden else "Create agency workspace",
            )
        if request.url.path == "/openapi.json":
            return httpx.Response(
                404 if schema_hidden else 200,
                headers=headers,
                json={"detail": "Not found."} if schema_hidden else {"openapi": "3.1.0"},
            )
        raise AssertionError(f"Unexpected deployment check request: {request.url}")

    return httpx.MockTransport(handler)


def _public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "veridra.deployment_acceptance.resolve_public_ips",
        lambda hostname: ["203.0.113.10"],
    )


def test_complete_deployment_contract_is_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    _public_dns(monkeypatch)

    result = run_deployment_acceptance(ORIGIN, transport=_transport())

    assert result.status is DeploymentCheckStatus.ok
    assert result.ready is True
    assert result.exit_code == 0
    assert all(check.status is DeploymentCheckStatus.ok for check in result.checks)
    payload = result.as_dict()
    assert payload["ready"] is True
    assert ORIGIN not in str(payload)
    assert "203.0.113.10" not in str(payload)


def test_unready_deployment_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _public_dns(monkeypatch)

    result = run_deployment_acceptance(
        ORIGIN,
        transport=_transport(ready=False),
    )

    checks = {check.name: check for check in result.checks}
    assert result.status is DeploymentCheckStatus.critical
    assert result.exit_code == 2
    assert checks["readiness"].status is DeploymentCheckStatus.critical


def test_missing_production_security_headers_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _public_dns(monkeypatch)

    result = run_deployment_acceptance(
        ORIGIN,
        transport=_transport(hsts=False),
    )

    checks = {check.name: check for check in result.checks}
    assert result.status is DeploymentCheckStatus.critical
    assert checks["security_headers"].status is DeploymentCheckStatus.critical


def test_public_onboarding_fails_deployment_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _public_dns(monkeypatch)

    result = run_deployment_acceptance(
        ORIGIN,
        transport=_transport(onboarding_hidden=False),
    )

    checks = {check.name: check for check in result.checks}
    assert result.status is DeploymentCheckStatus.critical
    assert checks["onboarding_exposure"].status is DeploymentCheckStatus.critical


def test_public_api_schema_fails_deployment_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _public_dns(monkeypatch)

    result = run_deployment_acceptance(
        ORIGIN,
        transport=_transport(schema_hidden=False),
    )

    checks = {check.name: check for check in result.checks}
    assert result.status is DeploymentCheckStatus.critical
    assert checks["schema_exposure"].status is DeploymentCheckStatus.critical


def test_invalid_or_nonpublic_origin_does_not_attempt_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "veridra.deployment_acceptance.resolve_public_ips",
        lambda hostname: (_ for _ in ()).throw(AssertionError("DNS should not run")),
    )
    result = run_deployment_acceptance("http://127.0.0.1:8000")

    assert result.status is DeploymentCheckStatus.critical
    assert [check.name for check in result.checks] == ["origin"]


def test_pinned_transport_preserves_tls_hostname_and_changes_socket_target() -> None:
    request = httpx.Request("GET", f"{ORIGIN}/health/live")

    pinned = _pin_deployment_request(
        request,
        hostname="app.example.test",
        ip_address="203.0.113.10",
    )

    assert pinned.url.host == "203.0.113.10"
    assert pinned.headers["host"] == "app.example.test"
    assert pinned.extensions["sni_hostname"] == "app.example.test"
