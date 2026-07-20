from __future__ import annotations

import zipfile
from io import BytesIO

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
    assert "name='url'" in response.text
    assert "/report?demo=true" in response.text
    assert "/export?demo=true" in response.text


def test_demo_api() -> None:
    payload = client.get("/api/demo").json()
    assert payload["summary"]["total"] > 0


def test_live_assessment_api(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = Assessment.build("https://example.com", [])
    monkeypatch.setattr(app_module, "assess_url", lambda url: expected)
    response = client.get("/api/assess", params={"url": "example.com"})
    assert response.status_code == 200
    assert response.json()["target"] == "https://example.com/"


def test_live_assessment_rejects_unsafe_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject(url: str) -> Assessment:
        raise UnsafeTargetError(
            "Non-public target address is not allowed: 127.0.0.1"
        )

    monkeypatch.setattr(app_module, "assess_url", reject)
    response = client.get("/api/assess", params={"url": "localhost"})
    assert response.status_code == 400
    assert "Non-public" in response.json()["detail"]


def test_live_dashboard_uses_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = Assessment.build("https://example.com", [])
    monkeypatch.setattr(app_module, "assess_url", lambda url: expected)
    response = client.get("/", params={"url": "example.com"})
    assert response.status_code == 200
    assert "value='example.com'" in response.text
    assert "/report?url=example.com" in response.text
    assert "/export?url=example.com" in response.text


def test_dashboard_displays_safe_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject(url: str) -> Assessment:
        raise UnsafeTargetError("Rejected <script>alert(1)</script>")

    monkeypatch.setattr(app_module, "assess_url", reject)
    response = client.get("/", params={"url": "localhost"})
    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "Rejected &lt;script&gt;alert(1)&lt;/script&gt;" in response.text


def test_demo_report_route() -> None:
    response = client.get("/report", params={"demo": "true"})
    assert response.status_code == 200
    assert "Veridra assessment report" in response.text
    assert "This is not a penetration test" in response.text


def test_report_requires_target() -> None:
    response = client.get("/report")
    assert response.status_code == 400


def test_demo_export_route() -> None:
    response = client.get("/export", params={"demo": "true"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "veridra-demo.veridra.local-evidence.zip" in response.headers[
        "content-disposition"
    ]
    assert response.headers["x-content-type-options"] == "nosniff"
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        assert "manifest.sha256" in archive.namelist()


def test_export_requires_target() -> None:
    response = client.get("/export")
    assert response.status_code == 400
