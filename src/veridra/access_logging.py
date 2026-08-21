from __future__ import annotations

import json
import logging
import secrets
import time
from collections.abc import Callable
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_LOGGER = logging.getLogger("veridra.access")
_REQUEST_ID_BYTES = 12
_UNMATCHED_ROUTE = "<unmatched>"


def _route_template(scope: Scope) -> str:
    route = scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path.startswith("/"):
        return path
    return _UNMATCHED_ROUTE


def _event(
    *,
    request_id: str,
    method: str,
    route: str,
    status_code: int,
    duration_ms: int,
) -> str:
    return json.dumps(
        {
            "duration_ms": max(0, duration_ms),
            "event": "http_request",
            "method": method,
            "request_id": request_id,
            "route": route,
            "status": status_code,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


class StructuredAccessLogMiddleware:
    """Emit privacy-minimized JSON access events for production HTTP requests."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        logger: logging.Logger | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.app = app
        self.logger = logger or _LOGGER
        self.clock = clock

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = secrets.token_hex(_REQUEST_ID_BYTES)
        started = self.clock()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers: list[tuple[bytes, bytes]] = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != b"x-request-id"
                ]
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            elapsed = self.clock() - started
            duration_ms = int(max(0.0, elapsed) * 1000)
            method = str(scope.get("method", "UNKNOWN"))[:16]
            self._write(
                _event(
                    request_id=request_id,
                    method=method,
                    route=_route_template(scope),
                    status_code=status_code,
                    duration_ms=duration_ms,
                )
            )

    def _write(self, payload: str) -> None:
        try:
            self.logger.info("%s", payload)
        except Exception:  # pragma: no cover - logging must never break request handling
            return
