from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .runtime_config import RuntimeEnvironment


class SecurityHeadersMiddleware:
    """Apply response hardening without breaking the intentional embed surface."""

    def __init__(self, app: ASGIApp, *, environment: RuntimeEnvironment) -> None:
        self.app = app
        self.environment = environment

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        embeddable = path.startswith("/embed/")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                names = {name.lower() for name, _ in headers}

                def add_if_missing(name: bytes, value: bytes) -> None:
                    if name.lower() not in names:
                        headers.append((name, value))
                        names.add(name.lower())

                add_if_missing(b"x-content-type-options", b"nosniff")
                add_if_missing(b"referrer-policy", b"strict-origin-when-cross-origin")
                add_if_missing(
                    b"permissions-policy",
                    b"camera=(), microphone=(), geolocation=()",
                )
                if embeddable:
                    add_if_missing(
                        b"content-security-policy",
                        b"object-src 'none'; base-uri 'self'",
                    )
                else:
                    add_if_missing(b"x-frame-options", b"DENY")
                    add_if_missing(
                        b"content-security-policy",
                        b"object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
                    )
                if self.environment is RuntimeEnvironment.production:
                    add_if_missing(
                        b"strict-transport-security",
                        b"max-age=31536000; includeSubDomains",
                    )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
