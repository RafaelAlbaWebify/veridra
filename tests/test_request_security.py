from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from veridra.identity_tenancy import (
    RequestIdentity,
    TenantCapability,
    TenantObjectRef,
    TenantRole,
)
from veridra.request_security import (
    authorize_tenant_object,
    bind_verified_request_identity,
    require_request_capability,
    require_request_identity,
)

NOW = datetime(2026, 7, 24, 12, 45, tzinfo=UTC)
TENANT_A = "a" * 24
TENANT_B = "b" * 24


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


def _identity(role: TenantRole = TenantRole.owner) -> RequestIdentity:
    return RequestIdentity(
        user_id="c" * 24,
        tenant_id=TENANT_A,
        membership_role=role,
        session_id="s" * 24,
        authenticated_at=NOW,
    )


def test_missing_or_untrusted_request_identity_fails_closed() -> None:
    request = _request()

    with pytest.raises(HTTPException) as missing:
        require_request_identity(request)
    assert missing.value.status_code == 401

    request.state.veridra_verified_identity = {
        "user_id": "c" * 24,
        "tenant_id": TENANT_A,
        "membership_role": "owner",
    }
    with pytest.raises(HTTPException) as untrusted:
        require_request_identity(request)
    assert untrusted.value.status_code == 401


def test_verified_identity_can_be_bound_by_trusted_adapter_boundary() -> None:
    request = _request()
    identity = _identity()

    bind_verified_request_identity(request, identity)

    assert require_request_identity(request) is identity


def test_capability_dependency_returns_identity_or_generic_forbidden() -> None:
    owner_request = _request()
    bind_verified_request_identity(owner_request, _identity(TenantRole.owner))
    owner_dependency = require_request_capability(TenantCapability.manage_projects)

    assert owner_dependency(owner_request).membership_role == TenantRole.owner

    viewer_request = _request()
    bind_verified_request_identity(viewer_request, _identity(TenantRole.viewer))
    with pytest.raises(HTTPException) as denied:
        owner_dependency(viewer_request)
    assert denied.value.status_code == 403
    assert denied.value.detail == "This action is not permitted."


def test_cross_tenant_target_is_hidden_as_not_found() -> None:
    request = _request()
    bind_verified_request_identity(request, _identity())
    target = TenantObjectRef(
        tenant_id=TENANT_B,
        object_type="project",
        object_id="shared-id",
    )

    with pytest.raises(HTTPException) as denied:
        authorize_tenant_object(request, target)

    assert denied.value.status_code == 404
    assert denied.value.detail == "Resource not found."


def test_same_tenant_target_can_require_capability() -> None:
    request = _request()
    bind_verified_request_identity(request, _identity(TenantRole.sales))
    target = TenantObjectRef(
        tenant_id=TENANT_A,
        object_type="lead",
        object_id="lead-1",
    )

    identity = authorize_tenant_object(
        request,
        target,
        capability=TenantCapability.manage_leads,
    )

    assert identity.membership_role == TenantRole.sales
