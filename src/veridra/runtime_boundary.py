from __future__ import annotations

from collections.abc import Awaitable, Callable

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


class RuntimeBoundaryMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        max_body_bytes: int,
        trusted_proxy_ips: tuple[str, ...] = (),
    ) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.trusted_proxy_ips = frozenset(trusted_proxy_ips)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        client = scope.get("client")
        peer = client[0] if client is not None else ""
        if any(name in headers for name in _FORWARDED_HEADERS) and peer not in self.trusted_proxy_ips:
            response = JSONResponse(
                {"detail": "Untrusted forwarded headers."},
                status_code=400,
            )
            await response(scope, receive, send)
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
                await self._reject_large_body(scope, receive, send)
                return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    raise _RequestBodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _RequestBodyTooLarge:
            await self._reject_large_body(scope, receive, send)

    @staticmethod
    async def _reject_large_body(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            {"detail": "Request body too large."},
            status_code=413,
        )
        await response(scope, receive, send)


class _RequestBodyTooLarge(Exception):
    pass
