from __future__ import annotations

import secrets
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .backup_restore import BackupRestoreError, create_backup
from .stripe_billing import StripeBillingError, StripeTenantBindingStore


class TenantOffboardingError(RuntimeError):
    pass


@dataclass(frozen=True)
class TenantOffboardingResult:
    tenant_id: str
    backup_archive: Path
    deleted_sessions: int
    deleted_invitations: int
    deleted_memberships: int
    deleted_monitoring_jobs: int


def _tenant_id(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != 24 or any(char not in "0123456789abcdef" for char in normalized):
        raise TenantOffboardingError("Tenant identifier must be 24 lowercase hexadecimal characters.")
    return normalized


def _identity_connect(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        is not None
    )


def _require_tenant(database: Path, tenant_id: str) -> None:
    if not database.is_file() or database.is_symlink():
        raise TenantOffboardingError("Identity database is unavailable.")
    try:
        with _identity_connect(database) as connection:
            row = connection.execute(
                "SELECT 1 FROM tenants WHERE id = ?",
                (tenant_id,),
            ).fetchone()
    except sqlite3.Error as exc:
        raise TenantOffboardingError("Tenant identity could not be validated.") from exc
    if row is None:
        raise TenantOffboardingError("Tenant was not found.")


def _monitoring_rows(database: Path, tenant_id: str) -> tuple[list[str], list[tuple[object, ...]]]:
    if not database.exists():
        return [], []
    if not database.is_file() or database.is_symlink():
        raise TenantOffboardingError("Monitoring job store is unavailable.")
    try:
        with sqlite3.connect(database) as connection:
            columns = [
                str(row[1])
                for row in connection.execute("PRAGMA table_info(monitoring_jobs)").fetchall()
            ]
            if not columns:
                return [], []
            quoted = ",".join(f'"{column}"' for column in columns)
            rows = connection.execute(
                f"SELECT {quoted} FROM monitoring_jobs WHERE tenant_id = ?",  # noqa: S608
                (tenant_id,),
            ).fetchall()
    except sqlite3.Error as exc:
        raise TenantOffboardingError("Monitoring jobs could not be inspected.") from exc
    return columns, [tuple(row) for row in rows]


def _delete_monitoring(database: Path, tenant_id: str) -> int:
    if not database.exists():
        return 0
    try:
        with sqlite3.connect(database) as connection:
            cursor = connection.execute(
                "DELETE FROM monitoring_jobs WHERE tenant_id = ?",
                (tenant_id,),
            )
            return cursor.rowcount
    except sqlite3.Error as exc:
        raise TenantOffboardingError("Monitoring jobs could not be removed.") from exc


def _restore_monitoring(
    database: Path,
    columns: list[str],
    rows: list[tuple[object, ...]],
) -> None:
    if not rows:
        return
    quoted = ",".join(f'"{column}"' for column in columns)
    placeholders = ",".join("?" for _ in columns)
    try:
        with sqlite3.connect(database) as connection:
            connection.executemany(
                f"INSERT INTO monitoring_jobs ({quoted}) VALUES ({placeholders})",  # noqa: S608
                rows,
            )
    except sqlite3.Error as exc:
        raise TenantOffboardingError(
            "Monitoring rollback failed; recover from the verified pre-offboarding backup."
        ) from exc


def _delete_identity(database: Path, tenant_id: str) -> tuple[int, int, int]:
    connection = _identity_connect(database)
    try:
        connection.execute("BEGIN IMMEDIATE")
        invitations = 0
        if _table_exists(connection, "tenant_invitations"):
            invitations = connection.execute(
                "DELETE FROM tenant_invitations WHERE tenant_id = ?",
                (tenant_id,),
            ).rowcount
        sessions = connection.execute(
            "DELETE FROM sessions WHERE tenant_id = ?",
            (tenant_id,),
        ).rowcount
        memberships = connection.execute(
            "DELETE FROM memberships WHERE tenant_id = ?",
            (tenant_id,),
        ).rowcount
        tenant = connection.execute(
            "DELETE FROM tenants WHERE id = ?",
            (tenant_id,),
        )
        if tenant.rowcount != 1:
            raise TenantOffboardingError("Tenant identity changed concurrently.")
        connection.commit()
        return sessions, invitations, memberships
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def offboard_tenant(
    *,
    identity_database: Path,
    tenant_data_root: Path,
    tenant_id: str,
    backup_output: Path,
    confirm_quiesced: bool,
    confirm_provider_billing_handled: bool = False,
) -> TenantOffboardingResult:
    if not confirm_quiesced:
        raise TenantOffboardingError(
            "Tenant offboarding requires explicit confirmation that web, worker and billing writers are quiesced."
        )
    identity_database = identity_database.expanduser().resolve()
    tenant_data_root = tenant_data_root.expanduser().resolve()
    backup_output = backup_output.expanduser().resolve()
    resolved_tenant = _tenant_id(tenant_id)
    _require_tenant(identity_database, resolved_tenant)

    tenant_directory = tenant_data_root / resolved_tenant
    if not tenant_directory.is_dir() or tenant_directory.is_symlink():
        raise TenantOffboardingError("Tenant durable directory is unavailable.")
    try:
        binding = StripeTenantBindingStore(tenant_data_root).load(resolved_tenant)
    except StripeBillingError as exc:
        raise TenantOffboardingError("Tenant billing binding could not be validated.") from exc
    if binding is not None and not confirm_provider_billing_handled:
        raise TenantOffboardingError(
            "Tenant has a Stripe subscription binding; confirm provider-side cancellation or transfer before offboarding."
        )

    try:
        backup = create_backup(
            identity_database=identity_database,
            tenant_data_root=tenant_data_root,
            output=backup_output,
            confirm_quiesced=True,
        )
    except BackupRestoreError as exc:
        raise TenantOffboardingError("Verified pre-offboarding backup could not be created.") from exc

    monitoring_database = tenant_data_root / "monitoring-jobs.sqlite3"
    columns, monitoring_rows = _monitoring_rows(monitoring_database, resolved_tenant)
    quarantine = tenant_data_root / f".offboarding-{resolved_tenant}-{secrets.token_hex(6)}"
    try:
        tenant_directory.replace(quarantine)
    except OSError as exc:
        raise TenantOffboardingError("Tenant durable state could not be staged for deletion.") from exc

    monitoring_deleted = False
    try:
        deleted_monitoring = _delete_monitoring(monitoring_database, resolved_tenant)
        monitoring_deleted = True
        deleted_sessions, deleted_invitations, deleted_memberships = _delete_identity(
            identity_database,
            resolved_tenant,
        )
    except Exception as exc:
        rollback_errors: list[Exception] = []
        if monitoring_deleted:
            try:
                _restore_monitoring(monitoring_database, columns, monitoring_rows)
            except Exception as rollback_exc:
                rollback_errors.append(rollback_exc)
        try:
            if quarantine.exists() and not tenant_directory.exists():
                quarantine.replace(tenant_directory)
        except OSError as rollback_exc:
            rollback_errors.append(rollback_exc)
        if rollback_errors:
            raise TenantOffboardingError(
                "Tenant offboarding failed and rollback was incomplete; recover from the verified backup."
            ) from exc
        if isinstance(exc, TenantOffboardingError):
            raise
        raise TenantOffboardingError("Tenant offboarding failed; staged state was restored.") from exc

    try:
        shutil.rmtree(quarantine)
    except OSError as exc:
        raise TenantOffboardingError(
            "Tenant identity was removed but quarantined durable state could not be erased; remove the quarantine directory manually."
        ) from exc

    return TenantOffboardingResult(
        tenant_id=resolved_tenant,
        backup_archive=backup.archive,
        deleted_sessions=deleted_sessions,
        deleted_invitations=deleted_invitations,
        deleted_memberships=deleted_memberships,
        deleted_monitoring_jobs=deleted_monitoring,
    )
