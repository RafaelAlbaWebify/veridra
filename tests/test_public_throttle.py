from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from veridra.public_throttle import PUBLIC_RATE_BUCKETS, enforce_public_rate_limit


@pytest.fixture(autouse=True)
def clear_public_rate_buckets() -> Iterator[None]:
    PUBLIC_RATE_BUCKETS.clear()
    yield
    PUBLIC_RATE_BUCKETS.clear()


def _client() -> TestClient:
    app = FastAPI()

    @app.get("/limited")
    def limited(request: Request) -> dict[str, bool]:
        enforce_public_rate_limit(request, namespace="test")
        return {"ok": True}

    return TestClient(app)


def test_production_internal_client_header_separates_proxy_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERIDRA_ENV", "production")
    client = _client()
    first = {"X-Veridra-Client-IP": "203.0.113.10"}
    second = {"X-Veridra-Client-IP": "203.0.113.11"}

    for _ in range(5):
        assert client.get("/limited", headers=first).status_code == 200

    assert client.get("/limited", headers=first).status_code == 429
    assert client.get("/limited", headers=second).status_code == 200


def test_invalid_internal_client_header_falls_back_to_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERIDRA_ENV", "production")
    client = _client()

    for index in range(5):
        response = client.get(
            "/limited",
            headers={"X-Veridra-Client-IP": f"not-an-ip-{index}"},
        )
        assert response.status_code == 200

    assert client.get(
        "/limited",
        headers={"X-Veridra-Client-IP": "still-not-an-ip"},
    ).status_code == 429
