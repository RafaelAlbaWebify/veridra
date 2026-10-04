from __future__ import annotations

import pytest
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


def test_local_agency_root_redirects_to_webify_console(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERIDRA_ENV", "production")
    monkeypatch.setenv("VERIDRA_LOCAL_AGENCY", "1")
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/agency"
