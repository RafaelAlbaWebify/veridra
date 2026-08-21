from __future__ import annotations

import sqlite3
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

import veridra.tenant_offboarding as offboarding_module
from veridra.identity_bootstrap import BOOTSTRAP_CONFIRMATION, SQLiteIdentityBootstrap
from veridra.monitoring_jobs import SQLiteMonitoringJobStore
from veridra.stripe_billing import StripeTenantBinding, StripeTenantBindingStore
from veridra.tenant_invitations import SQLiteTenantInvitationService
from veridra.tenant_offboarding import TenantOffboardingError, offboard_tenant

NOW = datetime(2026, 8, 21, 8, 30, tzinfo=UTC)
SECOND_TENANT = "b" * 24
PROJECT_ID = "c" * 24


def _setup(tmp_path: Path) -> tuple[Path, Path, str, str]:
    identity = tmp_path / "identity" / "identity.sqlite3"
    tenants = tmp_path / "tenants"
    created = SQLiteIdentityBootstrap(identity, tenant_data_root=tenants).create_first_owner(
        tenant_slug="target",
        tenant_name="Target tenant",
        owner_email="owner@example.com",
        owner_name="Owner",
        password="correct-horse-battery-owner",
        confirmation=BOOTSTRAP_CONFIRMATION,
        created_at=NOW,
    )
    with sqlite3.connect(identity) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """INSERT INTO tenants (id, slug, display_name, status, created_at)
            VALUES (?, 'other', 'Other tenant', 'active', ?)""",
            (SECOND_TENANT, NOW.isoformat()),
        )
        connection.execute(
            """INSERT INTO memberships (tenant_id, user_id, role, active, created_at)
            VALUES (?, ?, 'owner', 1, ?)""",
            (SECOND_TENANT, created.user_id, NOW.isoformat()),
        )
        connection.execute(
            """INSERT INTO sessions
            (id, credential_hash, user_id, tenant_id, status, issued_at, expires_at, revoked_at)
            VALUES (?, ?, ?, ?, 'active', ?, ?, NULL)""",
            (
                "d" * 24,
                "e" * 64,
                created.user_id,
                created.tenant_id,
                NOW.isoformat(),
                datetime(2026, 8, 22, 8, 30, tzinfo=UTC).isoformat(),
            ),
        )
    invitation_service = SQLiteTenantInvitationService(identity, tenants)
    invitation_service.issue(
        tenant_id=created.tenant_id,
        created_by_user_id=created.user_id,
        email="invitee@example.com",
        role=offboarding_module.TenantRole.analyst,
        now=NOW,
    )
    monitoring = SQLiteMonitoringJobStore(tenants / "monitoring-jobs.sqlite3")
    monitoring.enqueue(
        tenant_id=created.tenant_id,
        project_id=PROJECT_ID,
        run_window="2026-08-21",
        now=NOW,
    )
    target_marker = tenants / created.tenant_id / "customer-data.txt"
    target_marker.write_text("customer-secret-state", encoding="utf-8")
    return identity, tenants, created.tenant_id, created.user_id


def _count(database: Path, sql: str, parameters: tuple[str, ...]) -> int:
    with sqlite3.connect(database) as connection:
        return int(connection.execute(sql, parameters).fetchone()[0])


def test_offboarding_creates_backup_and_removes_only_tenant_context(tmp_path: Path) -> None:
    identity, tenants, tenant_id, user_id = _setup(tmp_path)
    backup = tmp_path / "recovery" / "before-offboarding.zip"

    result = offboard_tenant(
        identity_database=identity,
        tenant_data_root=tenants,
        tenant_id=tenant_id,
        backup_output=backup,
        confirm_quiesced=True,
    )

    assert result.tenant_id == tenant_id
    assert result.backup_archive == backup
    assert result.deleted_sessions == 1
    assert result.deleted_invitations == 1
    assert result.deleted_memberships == 1
    assert result.deleted_monitoring_jobs == 1
    assert backup.is_file()
    with zipfile.ZipFile(backup) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert f"tenants/{tenant_id}/customer-data.txt" in names
    assert not (tenants / tenant_id).exists()
    assert _count(identity, "SELECT COUNT(*) FROM tenants WHERE id = ?", (tenant_id,)) == 0
    assert _count(identity, "SELECT COUNT(*) FROM sessions WHERE tenant_id = ?", (tenant_id,)) == 0
    assert _count(identity, "SELECT COUNT(*) FROM memberships WHERE tenant_id = ?", (tenant_id,)) == 0
    assert _count(identity, "SELECT COUNT(*) FROM tenant_invitations WHERE tenant_id = ?", (tenant_id,)) == 0
    assert _count(identity, "SELECT COUNT(*) FROM users WHERE id = ?", (user_id,)) == 1
    assert _count(
        identity,
        "SELECT COUNT(*) FROM memberships WHERE tenant_id = ? AND user_id = ?",
        (SECOND_TENANT, user_id),
    ) == 1
    assert _count(
        tenants / "monitoring-jobs.sqlite3",
        "SELECT COUNT(*) FROM monitoring_jobs WHERE tenant_id = ?",
        (tenant_id,),
    ) == 0


def test_offboarding_refuses_stripe_bound_tenant_without_provider_acknowledgement(
    tmp_path: Path,
) -> None:
    identity, tenants, tenant_id, _ = _setup(tmp_path)
    StripeTenantBindingStore(tenants).save(
        StripeTenantBinding(
            tenant_id=tenant_id,
            customer_id="cus_target",
            subscription_id="sub_target",
            updated_at=NOW,
        )
    )
    backup = tmp_path / "recovery.zip"

    with pytest.raises(TenantOffboardingError, match="Stripe subscription binding"):
        offboard_tenant(
            identity_database=identity,
            tenant_data_root=tenants,
            tenant_id=tenant_id,
            backup_output=backup,
            confirm_quiesced=True,
        )

    assert not backup.exists()
    assert (tenants / tenant_id).is_dir()
    assert _count(identity, "SELECT COUNT(*) FROM tenants WHERE id = ?", (tenant_id,)) == 1


def test_offboarding_requires_quiescence_before_backup_or_mutation(tmp_path: Path) -> None:
    identity, tenants, tenant_id, _ = _setup(tmp_path)
    backup = tmp_path / "recovery.zip"

    with pytest.raises(TenantOffboardingError, match="quiesced"):
        offboard_tenant(
            identity_database=identity,
            tenant_data_root=tenants,
            tenant_id=tenant_id,
            backup_output=backup,
            confirm_quiesced=False,
        )

    assert not backup.exists()
    assert (tenants / tenant_id).is_dir()


def test_identity_failure_restores_staged_files_and_monitoring_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, tenants, tenant_id, _ = _setup(tmp_path)
    backup = tmp_path / "recovery.zip"

    def fail_identity(database: Path, selected_tenant: str) -> tuple[int, int, int]:
        raise RuntimeError("simulated identity failure")

    monkeypatch.setattr(offboarding_module, "_delete_identity", fail_identity)

    with pytest.raises(TenantOffboardingError, match="staged state was restored"):
        offboard_tenant(
            identity_database=identity,
            tenant_data_root=tenants,
            tenant_id=tenant_id,
            backup_output=backup,
            confirm_quiesced=True,
        )

    assert backup.is_file()
    assert (tenants / tenant_id / "customer-data.txt").read_text(encoding="utf-8") == (
        "customer-secret-state"
    )
    assert _count(identity, "SELECT COUNT(*) FROM tenants WHERE id = ?", (tenant_id,)) == 1
    assert _count(
        tenants / "monitoring-jobs.sqlite3",
        "SELECT COUNT(*) FROM monitoring_jobs WHERE tenant_id = ?",
        (tenant_id,),
    ) == 1
