from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException, Request, status

from .identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantCapability,
    TenantObjectRef,
    require_tenant_capability,
    require_tenant_scope,
)

_REQUEST_IDENTITY_STATE_KEY = "veridra_verified_identity"


class RequestSecurityError(RuntimeError):
    pass


def bind_verified_request_identity(request: Request, identity: RequestIdentity) -> None:
    """Bind identity already verified by a trusted server-side authentication adapter."""
    setattr(request.state, _REQUEST_IDENTITY_STATE_KEY, identity)


def require_request_identity(request: Request) -> RequestIdentity:
    candidate = getattr(request.state, _REQUEST_IDENTITY_STATE_KEY, None)
    if not isinstance(candidate, RequestIdentity):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
        )
    return candidate


def require_request_capability(
    capability: TenantCapability,
) -> Callable[[Request], RequestIdentity]:
    def dependency(request: Request) -> RequestIdentity:
        identity = require_request_identity(request)
        try:
            require_tenant_capability(identity, capability)
        except IdentityBoundaryError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This action is not permitted.",
            ) from exc
        return identity

    return dependency


def authorize_tenant_object(
    request: Request,
    target: TenantObjectRef,
    *,
    capability: TenantCapability | None = None,
) -> RequestIdentity:
    identity = require_request_identity(request)
    try:
        require_tenant_scope(identity, target)
    except IdentityBoundaryError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found.",
        ) from exc
    if capability is not None:
        try:
            require_tenant_capability(identity, capability)
        except IdentityBoundaryError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This action is not permitted.",
            ) from exc
    return identity
