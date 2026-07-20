from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import veridra.app as app_module
from veridra.app import app
from veridra.core import Assessment, UnsafeTargetError

client = TestClient(app)


def test_health() -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_dashboard_contract() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "AI discoverability" in response.text
    assert "not a penetration test" in response.text


def test_demo_api() -> None:
    payload = client.get("/api/demo").json()
    assert payload["summary"]["total"] > 0


def test_live_assessment_api(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = Assessment.build("https://example.com", [])
    monkeypatch.setattr(app_module, "assess_url", lambda url: expected)
    response = client.get("/api/assess", params={"url": "example.com"})
    assert response.status_code == 200
    assert response.json()["target"] == "https://example.com/"


def test_live_assessment_rejects_unsafe_target(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(url: str) -> Assessment:
        raise UnsafeTargetError("Non-public target address is not allowed: 127.0.0.1")

    monkeypatch.setattr(app_module, "assess_url", reject)
    response = client.get("/api/assess", params={"url": "localhost"})
    assert response.status_code == 400
    assert "Non-public" in response.json()["detail"]
