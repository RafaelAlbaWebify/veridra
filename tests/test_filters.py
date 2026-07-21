from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import veridra.app as app_module
from veridra.app import app, dashboard
from veridra.core import Assessment, Finding, Status

client = TestClient(app)


def _assessment() -> Assessment:
    return Assessment.build(
        "https://example.com",
        [
            Finding(
                id="health-pass",
                area="Website health",
                title="Healthy",
                status=Status.passed,
                severity="info",
                summary="Healthy response.",
            ),
            Finding(
                id="security-attention",
                area="Security posture",
                title="Missing policy",
                status=Status.attention,
                severity="medium",
                summary="Policy missing.",
                recommendation="Publish the policy.",
            ),
        ],
    )


def test_dashboard_filters_by_area_and_status() -> None:
    rendered = dashboard(
        _assessment(),
        demo_mode=True,
        area="Security posture",
        status="attention",
    )
    assert "1 of 2 findings displayed" in rendered
    assert "Missing policy" in rendered
    assert rendered.count("Healthy response.") == 0
    assert "area=Security+posture" in rendered
    assert "value='attention' selected" in rendered


def test_dashboard_empty_filter_state() -> None:
    rendered = dashboard(
        _assessment(),
        demo_mode=True,
        area="Website health",
        status="unavailable",
    )
    assert "0 of 2 findings displayed" in rendered
    assert "No findings match the selected filters" in rendered


def test_invalid_filters_are_rejected() -> None:
    assert client.get("/", params={"demo": "true", "area": "Unknown"}).status_code == 400
    assert client.get("/", params={"demo": "true", "status": "broken"}).status_code == 400


def test_live_target_is_preserved_in_area_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_module, "assess_url", lambda url: _assessment())
    response = client.get(
        "/",
        params={"url": "example.com", "area": "Security posture"},
    )
    assert response.status_code == 200
    assert "url=example.com&amp;area=Website+health" in response.text
    assert "value='example.com'" in response.text
    assert "1 of 2 findings displayed" in response.text
