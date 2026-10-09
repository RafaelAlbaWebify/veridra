from __future__ import annotations

import re

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .runtime_config import RuntimeEnvironment

_BASE_CSP = (
    "default-src 'none'; "
    "script-src 'none'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "form-action 'self'; "
    "frame-src 'none'; "
    "object-src 'none'; "
    "base-uri 'self'"
)

_BILLING_CSP = _BASE_CSP.replace(
    "form-action 'self'",
    "form-action 'self' https://checkout.stripe.com https://billing.stripe.com",
)


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
        market_base = r"/agency/prospects/discover/market/[a-f0-9]{32}"
        market_study_page = re.fullmatch(market_base, path) is not None
        market_map_frame = re.fullmatch(market_base + r"/map-view", path) is not None
        csp = _BILLING_CSP if path == "/billing" or path.startswith("/billing/") else _BASE_CSP
        if market_study_page:
            csp = csp.replace("frame-src 'none'", "frame-src 'self'")
            csp = csp.replace("script-src 'none'", "script-src 'self'")

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
                if market_map_frame:
                    add_if_missing(b"x-frame-options", b"SAMEORIGIN")
                    add_if_missing(
                        b"content-security-policy",
                        (csp + "; frame-ancestors 'self'").encode("ascii"),
                    )
                elif embeddable:
                    add_if_missing(
                        b"content-security-policy",
                        csp.encode("ascii"),
                    )
                else:
                    add_if_missing(b"x-frame-options", b"DENY")
                    add_if_missing(
                        b"content-security-policy",
                        f"{csp}; frame-ancestors 'none'".encode("ascii"),
                    )
                if self.environment is RuntimeEnvironment.production:
                    add_if_missing(
                        b"strict-transport-security",
                        b"max-age=31536000; includeSubDomains",
                    )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
