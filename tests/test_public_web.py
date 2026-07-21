from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import veridra.public_web as public_web
from veridra.app import app
from veridra.core import Assessment, Finding, Status, UnsafeTargetError

client = TestClient(app)


def _assessment() -> Assessment:
    return Assessment.build(
        "https://example.com",
        [
            Finding(
                id="ai-ready",
                area="AI discoverability",
                title="AI crawler access",
                status=Status.passed,
                severity="info",
                summary="Crawler access is available.",
            ),
            Finding(
                id="trust-contact",
                area="Trust signals",
                title="Contact route",
                status=Status.attention,
                severity="medium",
                summary="No obvious contact link was found.",
                recommendation="Add a clear contact page.",
            ),
            Finding(
                id="security-header",
                area="Security posture",
                title="Security header",
                status=Status.unavailable,
                severity="low",
                summary="The header could not be verified.",
            ),
        ],
    )


def test_free_home_requires_no_registration_and_hides_operator_data() -> None:
    response = client.get("/free")

    assert response.status_code == 200
    assert "no registration" in response.text.lower()
    assert "Website Audit" in response.text
    assert "Local Presence Readiness" in response.text
    assert "/projects" not in response.text
    assert "/profiles" not in response.text
    assert "/history" not in response.text


def test_tool_landing_page_has_labelled_public_url_input() -> None:
    response = client.get("/free/ai-readiness")

    assert response.status_code == 200
    assert "AI Readiness" in response.text
    assert "for='free-url'" in response.text
    assert "name='url'" in response.text
    assert "not whether an AI system mentions" in response.text


def test_tool_result_is_area_scoped_and_share_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(public_web, "assess_url", lambda url: _assessment())

    response = client.get(
        "/free/ai-readiness",
        params={"url": "example.com/?a=1&b=2"},
    )

    assert response.status_code == 200
    assert "AI crawler access" in response.text
    assert "Contact route" not in response.text
    assert "Security header" not in response.text
    assert "url=example.com%2F%3Fa%3D1%26b%3D2" in response.text
    assert "/projects" not in response.text


def test_local_presence_states_data_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(public_web, "assess_url", lambda url: _assessment())

    response = client.get("/free/local-presence", params={"url": "example.com"})

    assert response.status_code == 200
    boundary = (
        "Google Business Profile, Maps rankings, reviews and citations "
        "are not queried"
    )
    assert boundary in response.text
    assert "Contact route" in response.text
    assert "AI crawler access" not in response.text


def test_public_error_is_escaped(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(url: str) -> Assessment:
        raise UnsafeTargetError("Rejected <script>alert(1)</script>")

    monkeypatch.setattr(public_web, "assess_url", reject)
    response = client.get("/free/security-posture", params={"url": "localhost"})

    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "Rejected &lt;script&gt;alert(1)&lt;/script&gt;" in response.text


def test_unknown_free_tool_returns_404() -> None:
    response = client.get("/free/not-a-tool")

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown free tool."
