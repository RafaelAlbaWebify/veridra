from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from .identity_tenancy import RequestIdentity
from .request_security import bind_verified_request_identity
from .same_origin import SameOriginRequestError, TrustedSameOriginPolicy


class TrustedIdentityAdapter(Protocol):
    async def resolve(self, request: Request) -> RequestIdentity | None: ...


class VerifiedIdentityMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        adapter: TrustedIdentityAdapter,
        same_origin_policy: TrustedSameOriginPolicy | None = None,
    ) -> None:
        super().__init__(app)
        self.adapter = adapter
        self.same_origin_policy = same_origin_policy

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        identity = await self.adapter.resolve(request)
        if identity is not None:
            if self.same_origin_policy is not None:
                try:
                    self.same_origin_policy.validate(request)
                except SameOriginRequestError:
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Authenticated request origin is not permitted."},
                    )
            bind_verified_request_identity(request, identity)
        return await call_next(request)
