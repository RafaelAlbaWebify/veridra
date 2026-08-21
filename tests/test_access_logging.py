from __future__ import annotations

import io
import json
import logging
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from veridra.access_logging import StructuredAccessLogMiddleware

NOW = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)


def _logger() -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    logger = logging.Logger("veridra.access.test", level=logging.INFO)
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger, stream


def _client() -> tuple[TestClient, io.StringIO]:
    logger, stream = _logger()
    ticks = iter((10.0, 10.125, 20.0, 20.010, 30.0, 30.020))
    app = FastAPI()

    @app.post("/projects/{project_id}")
    async def project(project_id: str, request: Request) -> dict[str, str]:
        await request.body()
        return {"project_id": project_id}

    @app.get("/accept-invitation")
    def invitation() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(
        StructuredAccessLogMiddleware,
        logger=logger,
        clock=lambda: next(ticks),
        wall_clock=lambda: NOW,
    )
    return TestClient(app), stream


def _events(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


def test_access_log_uses_route_template_and_omits_sensitive_request_data() -> None:
    client, stream = _client()

    response = client.post(
        "/projects/project-secret-123?token=query-secret-456",
        headers={
            "authorization": "Bearer header-secret-789",
            "cookie": "session=cookie-secret-012",
            "x-request-id": "attacker-controlled-request-id",
        },
        content=b"body-secret-345",
    )

    assert response.status_code == 200
    event = _events(stream)[0]
    encoded = stream.getvalue()
    assert event["event"] == "http_request"
    assert event["method"] == "POST"
    assert event["route"] == "/projects/{project_id}"
    assert event["status"] == 200
    assert event["duration_ms"] == 125
    assert event["timestamp"] == NOW.isoformat()
    assert response.headers["x-request-id"] == event["request_id"]
    assert len(str(event["request_id"])) == 24
    for secret in (
        "project-secret-123",
        "query-secret-456",
        "header-secret-789",
        "cookie-secret-012",
        "attacker-controlled-request-id",
        "body-secret-345",
    ):
        assert secret not in encoded


def test_invitation_query_token_is_never_logged() -> None:
    client, stream = _client()

    response = client.get("/accept-invitation?token=invitation-secret-token")

    assert response.status_code == 200
    event = _events(stream)[0]
    assert event["route"] == "/accept-invitation"
    assert "invitation-secret-token" not in stream.getvalue()
    assert "?token=" not in stream.getvalue()


def test_unmatched_path_does_not_echo_attacker_controlled_path() -> None:
    client, stream = _client()

    response = client.get("/unknown/path-secret-value?token=query-secret-value")

    assert response.status_code == 404
    event = _events(stream)[0]
    assert event["route"] == "<unmatched>"
    assert event["status"] == 404
    assert "path-secret-value" not in stream.getvalue()
    assert "query-secret-value" not in stream.getvalue()
