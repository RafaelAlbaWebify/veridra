from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from veridra.runtime_boundary import RuntimeBoundaryMiddleware


def _client(*, hide_schema_routes: bool) -> TestClient:
    app = FastAPI()

    @app.get("/normal")
    def normal() -> dict[str, str]:
        return {"ok": "yes"}

    app.add_middleware(
        RuntimeBoundaryMiddleware,
        max_body_bytes=1_000_000,
        hide_schema_routes=hide_schema_routes,
    )
    return TestClient(app)


def test_schema_routes_remain_available_when_not_hidden() -> None:
    client = _client(hide_schema_routes=False)

    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/normal").json() == {"ok": "yes"}


def test_schema_and_interactive_docs_are_hidden_at_boundary() -> None:
    client = _client(hide_schema_routes=True)

    for path in (
        "/docs",
        "/docs/",
        "/docs/oauth2-redirect",
        "/redoc",
        "/redoc/",
        "/openapi.json",
    ):
        response = client.get(path)
        assert response.status_code == 404
        assert response.json() == {"detail": "Not found."}

    assert client.get("/normal").status_code == 200
