from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict

from .identity_tenancy import RequestIdentity, TenantCapability
from .project_store import ClientProject, ProjectEntry
from .request_security import authorize_tenant_object, require_request_capability
from .tenant_project_store import TenantProjectStore

router = APIRouter(prefix="/api/tenant/projects", tags=["tenant-projects"])


class TenantProjectSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    target_url: str
    client_label: str | None
    contact_label: str | None

    @classmethod
    def from_entry(cls, entry: ProjectEntry) -> TenantProjectSummary:
        return cls(
            id=entry.id,
            name=entry.name,
            target_url=entry.target_url,
            client_label=entry.client_label,
            contact_label=entry.contact_label,
        )


class TenantProjectCreated(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str


def _store() -> TenantProjectStore:
    return TenantProjectStore()


def build_tenant_project_router(*, root: Path | None = None) -> APIRouter:
    project_store = TenantProjectStore(root)
    api = APIRouter(prefix="/api/tenant/projects", tags=["tenant-projects"])

    @api.get("", response_model=list[TenantProjectSummary])
    def list_projects(
        identity: RequestIdentity = Depends(
            require_request_capability(TenantCapability.view_data)
        ),
    ) -> list[TenantProjectSummary]:
        return [TenantProjectSummary.from_entry(entry) for entry in project_store.list(identity)]

    @api.post("", response_model=TenantProjectCreated, status_code=status.HTTP_201_CREATED)
    def create_project(
        project: ClientProject,
        identity: RequestIdentity = Depends(
            require_request_capability(TenantCapability.manage_projects)
        ),
    ) -> TenantProjectCreated:
        return TenantProjectCreated(id=project_store.save(identity, project))

    @api.get("/{project_id}", response_model=ClientProject)
    def load_project(request: Request, project_id: str) -> ClientProject:
        identity = authorize_tenant_object(
            request,
            project_store.ref(
                require_request_capability(TenantCapability.view_data)(request),
                project_id,
            ),
        )
        return project_store.load(identity, project_store.ref(identity, project_id))

    @api.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_project(request: Request, project_id: str) -> None:
        identity = authorize_tenant_object(
            request,
            project_store.ref(
                require_request_capability(TenantCapability.manage_projects)(request),
                project_id,
            ),
            capability=TenantCapability.manage_projects,
        )
        project_store.delete(identity, project_store.ref(identity, project_id))

    return api


router = build_tenant_project_router()
