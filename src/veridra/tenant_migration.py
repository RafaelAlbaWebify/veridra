from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class MigrationBoundaryError(RuntimeError):
    pass


class MigrationStatus(StrEnum):
    planned = "planned"
    confirmed = "confirmed"
    applied = "applied"
    rolled_back = "rolled_back"


class MigrationRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    source_kind: str = Field(min_length=1, max_length=80)
    source_id: str = Field(min_length=1, max_length=160)
    source_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_object_type: str = Field(min_length=1, max_length=80)
    target_object_id: str = Field(min_length=1, max_length=160)

    @classmethod
    def from_source(
        cls,
        *,
        source_kind: str,
        source_id: str,
        source_bytes: bytes,
        target_object_type: str,
        target_object_id: str,
    ) -> MigrationRecord:
        return cls(
            source_kind=source_kind,
            source_id=source_id,
            source_checksum=hashlib.sha256(source_bytes).hexdigest(),
            target_object_type=target_object_type,
            target_object_id=target_object_id,
        )


class TenantMigrationManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    id: str = Field(pattern=r"^[0-9a-f]{24}$")
    target_tenant_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    source_root_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    records: tuple[MigrationRecord, ...] = Field(min_length=1)
    status: MigrationStatus = MigrationStatus.planned
    created_at: datetime
    confirmed_at: datetime | None = None
    applied_at: datetime | None = None
    rolled_back_at: datetime | None = None

    @classmethod
    def build(
        cls,
        *,
        target_tenant_id: str,
        source_root_fingerprint: str,
        records: tuple[MigrationRecord, ...],
        now: datetime | None = None,
    ) -> TenantMigrationManifest:
        created_at = (now or datetime.now(UTC)).astimezone(UTC)
        seed = json.dumps(
            {
                "target_tenant_id": target_tenant_id,
                "source_root_fingerprint": source_root_fingerprint,
                "records": [record.model_dump(mode="json") for record in records],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return cls(
            id=hashlib.sha256(seed).hexdigest()[:24],
            target_tenant_id=target_tenant_id,
            source_root_fingerprint=source_root_fingerprint,
            records=records,
            created_at=created_at,
        )


def confirm_manifest(
    manifest: TenantMigrationManifest,
    *,
    confirmed_target_tenant_id: str,
    now: datetime | None = None,
) -> TenantMigrationManifest:
    if manifest.status != MigrationStatus.planned:
        raise MigrationBoundaryError("Only a planned migration can be confirmed.")
    if manifest.target_tenant_id != confirmed_target_tenant_id:
        raise MigrationBoundaryError("Confirmed tenant does not match the migration target.")
    return manifest.model_copy(
        update={
            "status": MigrationStatus.confirmed,
            "confirmed_at": (now or datetime.now(UTC)).astimezone(UTC),
        }
    )


def mark_applied(
    manifest: TenantMigrationManifest,
    *,
    now: datetime | None = None,
) -> TenantMigrationManifest:
    if manifest.status != MigrationStatus.confirmed:
        raise MigrationBoundaryError("Migration must be confirmed before it is applied.")
    return manifest.model_copy(
        update={
            "status": MigrationStatus.applied,
            "applied_at": (now or datetime.now(UTC)).astimezone(UTC),
        }
    )


def mark_rolled_back(
    manifest: TenantMigrationManifest,
    *,
    now: datetime | None = None,
) -> TenantMigrationManifest:
    if manifest.status != MigrationStatus.applied:
        raise MigrationBoundaryError("Only an applied migration can be rolled back.")
    return manifest.model_copy(
        update={
            "status": MigrationStatus.rolled_back,
            "rolled_back_at": (now or datetime.now(UTC)).astimezone(UTC),
        }
    )
