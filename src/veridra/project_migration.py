from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .identity_tenancy import (
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .project_store import ClientProject, project_id
from .tenant_migration import (
    MigrationBoundaryError,
    MigrationRecord,
    MigrationStatus,
    TenantMigrationManifest,
    mark_applied,
    mark_rolled_back,
)
from .tenant_project_store import TenantProjectStore


class ProjectMigrationError(RuntimeError):
    pass


class ProjectMigrationEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    target_tenant_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    created_target_ids: tuple[str, ...]
    reused_target_ids: tuple[str, ...]
    source_checksums: dict[str, str]
    target_checksums: dict[str, str]


@dataclass(frozen=True)
class ProjectMigrationResult:
    manifest: TenantMigrationManifest
    evidence: ProjectMigrationEvidence


def _checksum(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _source_path(source_directory: Path, record: MigrationRecord) -> Path:
    if record.source_kind != "project_json" or record.target_object_type != "project":
        raise ProjectMigrationError("Migration record is not a project JSON record.")
    if Path(record.source_id).name != record.source_id:
        raise ProjectMigrationError("Migration source identifier is not a safe file name.")
    return source_directory / record.source_id


def plan_project_records(*, source_directory: Path) -> tuple[MigrationRecord, ...]:
    records: list[MigrationRecord] = []
    if not source_directory.exists():
        return ()
    for path in sorted(source_directory.glob("*.json")):
        payload = path.read_bytes()
        project = ClientProject.model_validate_json(payload)
        records.append(
            MigrationRecord.from_source(
                source_kind="project_json",
                source_id=path.name,
                source_bytes=payload,
                target_object_type="project",
                target_object_id=project_id(project),
            )
        )
    return tuple(records)


class ProjectMigrationExecutor:
    def __init__(self, *, source_directory: Path, target_root: Path) -> None:
        self.source_directory = source_directory
        self.target_store = TenantProjectStore(target_root)

    def apply(
        self,
        *,
        identity: RequestIdentity,
        manifest: TenantMigrationManifest,
    ) -> ProjectMigrationResult:
        require_tenant_capability(identity, TenantCapability.manage_projects)
        if identity.tenant_id != manifest.target_tenant_id:
            raise ProjectMigrationError("Migration target does not match the request tenant.")
        if manifest.status != MigrationStatus.confirmed:
            raise MigrationBoundaryError("Migration must be confirmed before it is applied.")

        created: list[str] = []
        reused: list[str] = []
        source_checksums: dict[str, str] = {}
        target_checksums: dict[str, str] = {}

        for record in manifest.records:
            source_path = _source_path(self.source_directory, record)
            try:
                source_bytes = source_path.read_bytes()
            except OSError as exc:
                raise ProjectMigrationError("Migration source could not be read.") from exc
            source_checksum = _checksum(source_bytes)
            if source_checksum != record.source_checksum:
                raise ProjectMigrationError("Migration source checksum changed after planning.")

            project = ClientProject.model_validate_json(source_bytes)
            if project_id(project) != record.target_object_id:
                raise ProjectMigrationError("Migration target identifier no longer matches source.")
            target_directory = self.target_store.root / identity.tenant_id / "projects"
            target_path = target_directory / f"{record.target_object_id}.json"
            if target_path.exists():
                target_bytes = target_path.read_bytes()
                if target_bytes != source_bytes:
                    raise ProjectMigrationError("Migration target collision has different content.")
                reused.append(record.target_object_id)
            else:
                saved_id = self.target_store.save(identity, project)
                if saved_id != record.target_object_id:
                    raise ProjectMigrationError("Migration target identifier changed during apply.")
                created.append(saved_id)

            written_bytes = target_path.read_bytes()
            target_checksum = _checksum(written_bytes)
            if target_checksum != source_checksum:
                raise ProjectMigrationError("Migration target checksum verification failed.")
            source_checksums[record.source_id] = source_checksum
            target_checksums[record.target_object_id] = target_checksum

        evidence = ProjectMigrationEvidence(
            manifest_id=manifest.id,
            target_tenant_id=manifest.target_tenant_id,
            created_target_ids=tuple(created),
            reused_target_ids=tuple(reused),
            source_checksums=source_checksums,
            target_checksums=target_checksums,
        )
        return ProjectMigrationResult(manifest=mark_applied(manifest), evidence=evidence)

    def rollback(
        self,
        *,
        identity: RequestIdentity,
        manifest: TenantMigrationManifest,
        evidence: ProjectMigrationEvidence,
    ) -> TenantMigrationManifest:
        require_tenant_capability(identity, TenantCapability.manage_projects)
        if manifest.status != MigrationStatus.applied:
            raise MigrationBoundaryError("Only an applied migration can be rolled back.")
        if identity.tenant_id != manifest.target_tenant_id:
            raise ProjectMigrationError("Migration target does not match the request tenant.")
        if evidence.manifest_id != manifest.id or evidence.target_tenant_id != identity.tenant_id:
            raise ProjectMigrationError("Rollback evidence does not match this migration.")

        for target_id in evidence.created_target_ids:
            target_path = (
                self.target_store.root
                / identity.tenant_id
                / "projects"
                / f"{target_id}.json"
            )
            if not target_path.exists():
                continue
            current_checksum = _checksum(target_path.read_bytes())
            expected_checksum = evidence.target_checksums[target_id]
            if current_checksum != expected_checksum:
                raise ProjectMigrationError("Rollback target changed after migration.")
            self.target_store.delete(identity, self.target_store.ref(identity, target_id))

        return mark_rolled_back(manifest)
