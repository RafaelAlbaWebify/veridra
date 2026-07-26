from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .identity_tenancy import RequestIdentity, TenantCapability, TenantObjectRef
from .request_security import require_request_capability
from .task_store import RemediationTask, TaskStatus
from .tenant_project_store import TenantProjectStore, TenantProjectStoreError
from .tenant_task_store import TenantTaskStore, TenantTaskStoreError

router = APIRouter(prefix="/api/tenant/tasks", tags=["tenant-tasks"])
TaskReader = Annotated[
    RequestIdentity,
    Depends(require_request_capability(TenantCapability.view_data)),
]
TaskManager = Annotated[
    RequestIdentity,
    Depends(require_request_capability(TenantCapability.manage_tasks)),
]


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _store(request: Request) -> TenantTaskStore:
    return TenantTaskStore(_root(request))


def _project_store(request: Request) -> TenantProjectStore:
    return TenantProjectStore(_root(request))


def _target(identity: RequestIdentity, task_id: str) -> TenantObjectRef:
    return TenantTaskStore.ref(identity, task_id)


def _require_project(request: Request, identity: RequestIdentity, project_id: str) -> None:
    try:
        _project_store(request).load(
            identity,
            TenantObjectRef(
                tenant_id=identity.tenant_id,
                object_type="project",
                object_id=project_id,
            ),
        )
    except TenantProjectStoreError as exc:
        raise HTTPException(status_code=404, detail="Project not found.") from exc


@router.get("")
def list_tasks(
    request: Request,
    identity: TaskReader,
    project_id: str | None = None,
    status_filter: TaskStatus | None = None,
) -> list[dict[str, object]]:
    if project_id is not None:
        _require_project(request, identity, project_id)
    return [
        {"id": task_id, **task.model_dump(mode="json")}
        for task_id, task in _store(request).list(
            identity,
            project_id=project_id,
            status=status_filter,
        )
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_task(
    payload: RemediationTask,
    request: Request,
    identity: TaskManager,
) -> dict[str, str]:
    _require_project(request, identity, payload.project_id)
    return {"id": _store(request).save(identity, payload)}


@router.get("/{task_id}", response_model=RemediationTask)
def get_task(task_id: str, request: Request, identity: TaskReader) -> RemediationTask:
    try:
        return _store(request).load(identity, _target(identity, task_id))
    except TenantTaskStoreError as exc:
        raise HTTPException(status_code=404, detail="Task not found.") from exc


@router.put("/{task_id}", response_model=RemediationTask)
def replace_task(
    task_id: str,
    payload: RemediationTask,
    request: Request,
    identity: TaskManager,
) -> RemediationTask:
    _require_project(request, identity, payload.project_id)
    try:
        replacement_id = _store(request).replace(
            identity,
            _target(identity, task_id),
            payload,
        )
        return _store(request).load(identity, _target(identity, replacement_id))
    except TenantTaskStoreError as exc:
        raise HTTPException(status_code=404, detail="Task not found.") from exc


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: str, request: Request, identity: TaskManager) -> None:
    try:
        _store(request).delete(identity, _target(identity, task_id))
    except TenantTaskStoreError as exc:
        raise HTTPException(status_code=404, detail="Task not found.") from exc
