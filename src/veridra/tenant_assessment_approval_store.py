from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel, ConfigDict, Field

from .identity_tenancy import RequestIdentity, TenantCapability, require_tenant_capability
from .tenant_project_store import default_tenant_data_directory


class AssessmentApproval(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    assessment_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    approved_at: datetime
    approved_by: str = Field(min_length=1, max_length=200)
    note: str = Field(default="", max_length=2000)


class TenantAssessmentApprovalStoreError(RuntimeError):
    pass


class TenantAssessmentApprovalStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_tenant_data_directory()

    def _path(self, identity: RequestIdentity, project_id: str, assessment_id: str) -> Path:
        for value in (project_id, assessment_id):
            if len(value) != 24 or any(char not in "0123456789abcdef" for char in value):
                raise TenantAssessmentApprovalStoreError("Invalid assessment approval identifier.")
        return (
            self.root
            / identity.tenant_id
            / "projects"
            / project_id
            / "assessment-approvals"
            / f"{assessment_id}.json"
        )

    def load(
        self,
        identity: RequestIdentity,
        project_id: str,
        assessment_id: str,
    ) -> AssessmentApproval | None:
        require_tenant_capability(identity, TenantCapability.view_data)
        path = self._path(identity, project_id, assessment_id)
        try:
            return AssessmentApproval.model_validate_json(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            raise TenantAssessmentApprovalStoreError(
                "Assessment approval could not be read safely."
            ) from exc

    def approve(
        self,
        identity: RequestIdentity,
        project_id: str,
        assessment_id: str,
        *,
        note: str = "",
    ) -> AssessmentApproval:
        require_tenant_capability(identity, TenantCapability.manage_reports)
        approval = AssessmentApproval(
            project_id=project_id,
            assessment_id=assessment_id,
            approved_at=datetime.now(UTC),
            approved_by=identity.subject,
            note=note.strip(),
        )
        path = self._path(identity, project_id, assessment_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            approval.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        with NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{assessment_id}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)
        return approval
