from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from veridra.agency_workflow_web import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_agency_home_explains_quick_and_persistent_workflows() -> None:
    response = _client().get("/agency")

    assert response.status_code == 200
    assert "Turn website evidence into client work" in response.text
    assert "Quick audit" in response.text
    assert "Client projects" in response.text
    assert "does not create a project or save data automatically" in response.text
    assert "Veridra does not infer a tenant, client or project" in response.text
    assert "href='/profiles'" in response.text
    assert "href='/monitoring'" in response.text


def test_quick_audit_handoff_redirects_to_existing_console_without_persistence() -> None:
    response = _client().get(
        "/agency/quick-audit",
        params={"target": "  https://example.com/path?a=1&b=2  "},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/?url=https%3A%2F%2Fexample.com%2Fpath%3Fa%3D1%26b%3D2"


def test_quick_audit_handoff_rejects_missing_target() -> None:
    response = _client().get("/agency/quick-audit", follow_redirects=False)

    assert response.status_code == 422


def test_quick_audit_handoff_does_not_reflect_target_in_response_body() -> None:
    marker = "<script>alert(1)</script>"
    response = _client().get(
        "/agency/quick-audit",
        params={"target": marker},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert marker not in response.text
    assert response.headers["location"].startswith("/?url=")
