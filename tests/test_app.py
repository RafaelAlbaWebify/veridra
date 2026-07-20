from fastapi.testclient import TestClient

from veridra.app import app

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
