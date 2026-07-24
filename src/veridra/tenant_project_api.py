from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict

from .identity_tenancy import RequestIdentity, TenantCapability
from .project_store import ClientProject, ProjectEntry
from .request_security import require_request_capability
from .tenant_project_store import TenantProjectStore


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
    def load_project(
        project_id: str,
        identity: RequestIdentity = Depends(
            require_request_capability(TenantCapability.view_data)
        ),
    ) -> ClientProject:
        return project_store.load(identity, project_store.ref(identity, project_id))

    @api.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_project(
        project_id: str,
        identity: RequestIdentity = Depends(
            require_request_capability(TenantCapability.manage_projects)
        ),
    ) -> None:
        project_store.delete(identity, project_store.ref(identity, project_id))

    return api


router = build_tenant_project_router()
