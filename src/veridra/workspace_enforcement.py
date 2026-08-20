from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse

from .request_security import require_request_identity
from .tenant_entitlements import (
    record_tenant_usage,
    require_tenant_feature,
    require_tenant_project_capacity,
    reserve_tenant_usage,
    tenant_workspace_active,
)
from .tenant_project_store import TenantProjectStore, TenantProjectStoreError
from .tenant_workspace_policy import TenantWorkspacePolicy
from .workspace_policy import UsageKind

NextHandler = Callable[[Request], Awaitable[Response]]


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _profile_write(path: str, method: str) -> bool:
    if method not in {"POST", "PUT"}:
        return False
    return path.startswith("/api/tenant/report-profiles") or (
        path.startswith("/agency/projects/")
        and (
            path.endswith("/reports/profile/create")
            or path.endswith("/reports/profile/edit")
        )
    )


def _lead_form_write(path: str, method: str) -> bool:
    if method not in {"POST", "PUT"}:
        return False
    if path.startswith("/api/tenant/lead-forms"):
        return True
    return path == "/agency/lead-forms" or (
        path.startswith("/agency/lead-forms/") and path.endswith("/edit")
    )


def _monitoring_write(path: str, method: str) -> bool:
    if method != "POST":
        return False
    return (
        path.endswith("/monitoring/run")
        or path.endswith("/monitor/run")
        or path == "/api/tenant/monitoring/run-due"
    )


def _tenant_pdf(path: str, method: str) -> bool:
    return (
        method == "GET"
        and path.startswith("/api/tenant/projects/")
        and path.endswith("/report.pdf")
    )


def _tenant_export(path: str, method: str) -> bool:
    return (
        method == "GET"
        and path.startswith("/api/tenant/projects/")
        and path.endswith("/export")
    )


def _project_id(path: str) -> str | None:
    prefixes = ("/agency/projects/", "/api/tenant/projects/")
    for prefix in prefixes:
        if path.startswith(prefix):
            remainder = path[len(prefix) :]
            candidate = remainder.split("/", 1)[0]
            return candidate or None
    return None


def _project_uses_white_label(request: Request, project_id: str) -> bool:
    identity = require_request_identity(request)
    projects = TenantProjectStore(_root(request))
    try:
        project = projects.load(identity, projects.ref(identity, project_id))
    except TenantProjectStoreError:
        return False
    return project.profile_id is not None


def _branded_report_use(path: str, method: str) -> bool:
    if path.startswith("/api/tenant/projects/") and method == "GET":
        return path.endswith(("/report", "/report.pdf", "/export"))
    return (
        path.startswith("/agency/projects/")
        and path.endswith("/reports/send")
        and method in {"GET", "POST"}
    )


def _preflight(
    request: Request,
    policy: TenantWorkspacePolicy,
) -> list[tuple[UsageKind, int, str]]:
    identity = require_request_identity(request)
    path = request.url.path
    method = request.method.upper()
    metered: list[tuple[UsageKind, int, str]] = []

    if method == "POST" and path == "/api/tenant/projects/from-assessment":
        projects = TenantProjectStore(_root(request))
        require_tenant_project_capacity(
            policy,
            identity,
            len(projects.list(identity)),
        )

    if _profile_write(path, method):
        require_tenant_feature(policy, identity, "white_label")

    if _lead_form_write(path, method):
        require_tenant_feature(policy, identity, "embedded_lead_forms")

    project_id = _project_id(path)
    if (
        project_id is not None
        and _branded_report_use(path, method)
        and _project_uses_white_label(request, project_id)
    ):
        require_tenant_feature(policy, identity, "white_label")

    if _monitoring_write(path, method):
        reserve_tenant_usage(policy, identity, UsageKind.monitoring_run)
        metered.append((UsageKind.monitoring_run, 1, path))

    if _tenant_pdf(path, method):
        reserve_tenant_usage(policy, identity, UsageKind.pdf)
        metered.append((UsageKind.pdf, 1, path))

    if _tenant_export(path, method):
        reserve_tenant_usage(policy, identity, UsageKind.export)
        metered.append((UsageKind.export, 1, path))

    return metered


async def enforce_workspace_policy(request: Request, call_next: NextHandler) -> Response:
    try:
        identity = require_request_identity(request)
    except HTTPException:
        return await call_next(request)

    policy = TenantWorkspacePolicy(_root(request))
    if not tenant_workspace_active(policy, identity):
        return await call_next(request)

    path = request.url.path
    if path.startswith("/free/") or path.startswith("/crawl/"):
        return await call_next(request)

    try:
        metered = _preflight(request, policy)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    response = await call_next(request)
    if response.status_code < 400:
        for kind, quantity, related_id in metered:
            record_tenant_usage(
                policy,
                identity,
                kind,
                quantity=quantity,
                related_id=related_id,
                note="Commercial route usage",
            )
    return response
