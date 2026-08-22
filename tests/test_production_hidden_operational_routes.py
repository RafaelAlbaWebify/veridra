from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from veridra.runtime_boundary import RuntimeBoundaryMiddleware


def _client(*, production: bool) -> TestClient:
    app = FastAPI()

    @app.get("/health")
    def legacy_health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def legacy_ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready() -> dict[str, str]:
        return {"status": "ok"}

    app.add_middleware(
        RuntimeBoundaryMiddleware,
        max_body_bytes=1_000_000,
        hide_schema_routes=production,
    )
    return TestClient(app)


def test_production_hides_legacy_health_aliases_but_keeps_canonical_routes() -> None:
    client = _client(production=True)

    assert client.get("/health").status_code == 404
    assert client.get("/ready").status_code == 404
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200


def test_nonproduction_keeps_legacy_health_aliases_for_compatibility() -> None:
    client = _client(production=False)

    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200
