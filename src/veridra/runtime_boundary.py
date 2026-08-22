from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_FORWARDED_HEADERS = {
    b"forwarded",
    b"x-forwarded-for",
    b"x-forwarded-host",
    b"x-forwarded-port",
    b"x-forwarded-proto",
}
_SCHEMA_PATHS = frozenset({"/docs", "/redoc", "/openapi.json"})


def _schema_path(path: str) -> bool:
    return path in _SCHEMA_PATHS or path.startswith("/docs/") or path.startswith("/redoc/")


class RuntimeBoundaryMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        max_body_bytes: int,
        trusted_proxy_ips: tuple[str, ...] = (),
        hide_schema_routes: bool = False,
    ) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.trusted_proxy_ips = frozenset(trusted_proxy_ips)
        self.hide_schema_routes = hide_schema_routes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path", ""))
        if self.hide_schema_routes and _schema_path(path):
            await self._reject(scope, receive, send, 404, "Not found.")
            return
        headers = dict(scope.get("headers", []))
        client = scope.get("client")
        peer = client[0] if client is not None else ""
        forwarded_present = any(name in headers for name in _FORWARDED_HEADERS)
        if forwarded_present and peer not in self.trusted_proxy_ips:
            await self._reject(scope, receive, send, 400, "Untrusted forwarded headers.")
            return
        if scope.get("method") not in _UNSAFE_METHODS:
            await self.app(scope, receive, send)
            return
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except ValueError:
                declared_length = self.max_body_bytes + 1
            if declared_length > self.max_body_bytes:
                await self._reject(scope, receive, send, 413, "Request body too large.")
                return

        messages: list[Message] = []
        received = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    await self._reject(scope, receive, send, 413, "Request body too large.")
                    return
                if not message.get("more_body", False):
                    break
            elif message["type"] == "http.disconnect":
                break

        index = 0

        async def replay_receive() -> Message:
            nonlocal index
            if index < len(messages):
                message = messages[index]
                index += 1
                return message
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _reject(
        scope: Scope,
        receive: Receive,
        send: Send,
        status_code: int,
        detail: str,
    ) -> None:
        response = JSONResponse({"detail": detail}, status_code=status_code)
        await response(scope, receive, send)
