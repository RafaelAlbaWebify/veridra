from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from veridra.public_web import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_free_home_exposes_signup_and_login_conversion_paths() -> None:
    response = _client().get("/free")

    assert response.status_code == 200
    assert "href='/signup'" in response.text
    assert "Create agency workspace" in response.text
    assert "href='/login'" in response.text
    assert "Turn audits into client work" in response.text


def test_free_tool_landing_keeps_signup_conversion_visible() -> None:
    response = _client().get("/free/website-audit")

    assert response.status_code == 200
    assert "href='/signup'" in response.text
    assert "Create agency workspace" in response.text
    assert "href='/login'" in response.text
    assert "persistent client projects" in response.text
