from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse

from .project_store import ProjectStore
from .workspace_policy import UsageKind
from .workspace_web import (
    record_usage,
    require_feature,
    require_project_capacity,
    reserve_usage,
    workspace_policy_active,
)

NextHandler = Callable[[Request], Awaitable[Response]]


def _is_identifier(value: str) -> bool:
    return len(value) == 24 and all(char in "0123456789abcdef" for char in value)


def _profile_write(path: str, method: str) -> bool:
    if method != "POST":
        return False
    parts = path.strip("/").split("/")
    return parts == ["profiles"] or (
        len(parts) == 2 and parts[0] == "profiles" and _is_identifier(parts[1])
    )


def _embedded_form_path(path: str) -> bool:
    parts = path.strip("/").split("/")
    return len(parts) == 3 and parts[:2] == ["embed", "audit"]


def _monitoring_write(path: str, method: str) -> bool:
    if method != "POST":
        return False
    return path == "/monitoring/run-due" or path.endswith("/monitor/run") or (
        path.startswith("/monitoring/projects/") and path.endswith("/run")
    )


def _legacy_pdf(path: str, method: str) -> bool:
    return method == "GET" and path == "/report.pdf"


def _legacy_export(path: str, method: str) -> bool:
    return method == "GET" and path == "/export"


def _retry_kind(path: str, method: str) -> UsageKind | None:
    if method != "POST":
        return None
    if path.endswith("/delivery/retry"):
        return UsageKind.webhook_attempt
    if path.endswith("/email/retry"):
        return UsageKind.email_attempt
    return None


def _preflight(request: Request) -> list[tuple[UsageKind, int, str]]:
    path = request.url.path
    method = request.method.upper()
    metered: list[tuple[UsageKind, int, str]] = []

    if method == "POST" and path == "/projects":
        require_project_capacity(len(ProjectStore().list()))

    if _profile_write(path, method):
        require_feature("white_label")

    if request.query_params.get("profile") and path in {"/report", "/report.pdf", "/export"}:
        require_feature("white_label")

    if method == "POST" and path == "/lead-forms":
        require_feature("embedded_lead_forms")

    if _embedded_form_path(path):
        require_feature("embedded_lead_forms")
        if method == "POST":
            reserve_usage(UsageKind.lead_submission)
            metered.append((UsageKind.lead_submission, 1, path.rsplit("/", 1)[-1]))

    if _monitoring_write(path, method):
        reserve_usage(UsageKind.monitoring_run)
        metered.append((UsageKind.monitoring_run, 1, path))

    if _legacy_pdf(path, method):
        reserve_usage(UsageKind.pdf)
        metered.append((UsageKind.pdf, 1, request.query_params.get("url", "")))

    if _legacy_export(path, method):
        reserve_usage(UsageKind.export)
        metered.append((UsageKind.export, 1, request.query_params.get("url", "")))

    retry_kind = _retry_kind(path, method)
    if retry_kind is not None:
        metered.append((retry_kind, 1, path))
    return metered


async def enforce_workspace_policy(request: Request, call_next: NextHandler) -> Response:
    if not workspace_policy_active():
        return await call_next(request)

    path = request.url.path
    if path.startswith("/free/") or path.startswith("/crawl/"):
        return await call_next(request)

    try:
        metered = _preflight(request)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    response = await call_next(request)
    if response.status_code < 400:
        for kind, quantity, related_id in metered:
            record_usage(
                kind,
                quantity=quantity,
                related_id=related_id,
                note="Commercial route usage",
            )
    return response
