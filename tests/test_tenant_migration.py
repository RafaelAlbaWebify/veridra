from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from veridra.tenant_migration import (
    MigrationBoundaryError,
    MigrationRecord,
    MigrationStatus,
    TenantMigrationManifest,
    confirm_manifest,
    mark_applied,
    mark_rolled_back,
)

NOW = datetime(2026, 7, 24, 13, 0, tzinfo=UTC)
TENANT_ID = "a" * 24
SOURCE_ROOT_FINGERPRINT = hashlib.sha256(b"/local/veridra-data").hexdigest()


def _record(source_id: str = "project-1") -> MigrationRecord:
    return MigrationRecord.from_source(
        source_kind="project_json",
        source_id=source_id,
        source_bytes=b'{"name":"Example"}',
        target_object_type="project",
        target_object_id=source_id,
    )


def _manifest() -> TenantMigrationManifest:
    return TenantMigrationManifest.build(
        target_tenant_id=TENANT_ID,
        source_root_fingerprint=SOURCE_ROOT_FINGERPRINT,
        records=(_record(),),
        now=NOW,
    )


def test_migration_record_preserves_source_checksum() -> None:
    record = _record()

    assert record.source_checksum == hashlib.sha256(b'{"name":"Example"}').hexdigest()


def test_manifest_identifier_is_stable_for_same_inventory() -> None:
    first = _manifest()
    second = _manifest()

    assert first.id == second.id
    assert first.status == MigrationStatus.planned
    assert first.confirmed_at is None


def test_manifest_requires_explicit_matching_tenant_confirmation() -> None:
    manifest = _manifest()

    with pytest.raises(MigrationBoundaryError, match="does not match"):
        confirm_manifest(
            manifest,
            confirmed_target_tenant_id="b" * 24,
            now=NOW + timedelta(minutes=1),
        )

    confirmed = confirm_manifest(
        manifest,
        confirmed_target_tenant_id=TENANT_ID,
        now=NOW + timedelta(minutes=1),
    )

    assert confirmed.status == MigrationStatus.confirmed
    assert confirmed.confirmed_at == NOW + timedelta(minutes=1)


def test_manifest_enforces_confirm_apply_rollback_order() -> None:
    manifest = _manifest()

    with pytest.raises(MigrationBoundaryError, match="confirmed"):
        mark_applied(manifest, now=NOW + timedelta(minutes=2))

    confirmed = confirm_manifest(
        manifest,
        confirmed_target_tenant_id=TENANT_ID,
        now=NOW + timedelta(minutes=1),
    )
    applied = mark_applied(confirmed, now=NOW + timedelta(minutes=2))
    rolled_back = mark_rolled_back(applied, now=NOW + timedelta(minutes=3))

    assert applied.status == MigrationStatus.applied
    assert applied.applied_at == NOW + timedelta(minutes=2)
    assert rolled_back.status == MigrationStatus.rolled_back
    assert rolled_back.rolled_back_at == NOW + timedelta(minutes=3)


def test_non_applied_manifest_cannot_be_marked_rolled_back() -> None:
    with pytest.raises(MigrationBoundaryError, match="applied"):
        mark_rolled_back(_manifest(), now=NOW + timedelta(minutes=1))
