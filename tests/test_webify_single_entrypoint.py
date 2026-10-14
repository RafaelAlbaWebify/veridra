from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from veridra.landing_web import router


def test_root_always_opens_webify_agency_console() -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, follow_redirects=False)

    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["location"] == "/agency"
