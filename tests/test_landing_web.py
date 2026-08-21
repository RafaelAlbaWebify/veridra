from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from veridra.landing_web import router


def test_public_root_redirects_to_free_tools() -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/free"
