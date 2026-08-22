from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from veridra.agency_workflow_web import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_agency_home_explains_acquisition_and_persistent_workflows() -> None:
    response = _client().get("/agency")

    assert response.status_code == 200
    assert "Find refurbishment opportunities and turn evidence into client work" in response.text
    assert "1. Discover" in response.text
    assert "2. Qualify" in response.text
    assert "3. Audit" in response.text
    assert "4. Win work" in response.text
    assert "5. Prove" in response.text
    assert "Webify prospects" in response.text
    assert "Quick audit" in response.text
    assert "Client projects" in response.text
    assert "A prospect is outbound Webify research" in response.text
    assert "website audit remains temporary until an operator explicitly creates" in response.text
    assert "href='/agency/prospects'" in response.text
    assert "href='/agency/projects'" in response.text
    assert "href='/agency/leads'" in response.text
    assert "href='/agency/lead-forms'" in response.text
    assert "href='/workspace'" in response.text
    assert "href='/workspace/members'" in response.text


def test_agency_home_does_not_expose_global_compatibility_routes() -> None:
    response = _client().get("/agency")

    assert response.status_code == 200
    assert "href='/profiles'" not in response.text
    assert "href='/commercial'" not in response.text
    assert "href='/projects'" not in response.text
    assert "href='/monitoring'" not in response.text
    assert "href='/leads'" not in response.text
    assert "href='/lead-forms'" not in response.text


def test_quick_audit_handoff_redirects_to_completed_agency_result() -> None:
    response = _client().get(
        "/agency/quick-audit",
        params={"target": "  https://example.com/path?a=1&b=2  "},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        "/agency/audit?url=https%3A%2F%2Fexample.com%2Fpath%3Fa%3D1%26b%3D2"
    )


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
    assert response.headers["location"].startswith("/agency/audit?url=")
