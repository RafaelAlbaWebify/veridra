from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


class RecoveryReadinessError(RuntimeError):
    pass


@dataclass(frozen=True)
class RecoveryReadinessSummary:
    users: int
    tenants: int
    projects: int
    assessments: int
    report_evidence: int
    monitoring_jobs: int


def _sqlite_count(database: Path, table: str) -> int:
    if not database.is_file():
        raise RecoveryReadinessError(f"Required SQLite database is missing: {database}")
    try:
        with sqlite3.connect(database) as connection:
            row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    except sqlite3.Error as exc:
        raise RecoveryReadinessError(
            f"Required SQLite table {table!r} could not be read from {database.name}."
        ) from exc
    return int(row[0]) if row is not None else 0


def validate_recovery_readiness(
    *,
    identity_database: Path,
    tenant_data_root: Path,
) -> RecoveryReadinessSummary:
    identity_database = identity_database.expanduser().resolve()
    tenant_data_root = tenant_data_root.expanduser().resolve()

    users = _sqlite_count(identity_database, "users")
    tenants = _sqlite_count(identity_database, "tenants")
    if users < 1 or tenants < 1:
        raise RecoveryReadinessError(
            "Restored identity state does not contain a usable operator and tenant."
        )

    if not tenant_data_root.is_dir():
        raise RecoveryReadinessError(
            f"Restored tenant data root is missing: {tenant_data_root}"
        )

    projects = len(list(tenant_data_root.glob("*/projects/*.json")))
    assessments = len(
        list(tenant_data_root.glob("*/projects/*/assessments/*.json"))
    )
    report_evidence = sum(
        len(list(tenant_data_root.glob(pattern)))
        for pattern in (
            "*/report-profiles/*.json",
            "*/projects/*/assessment-approvals/*.json",
            "*/report-deliveries/*.json",
        )
    )

    monitoring_database = tenant_data_root / "monitoring-jobs.sqlite3"
    monitoring_jobs = _sqlite_count(monitoring_database, "monitoring_jobs")

    missing: list[str] = []
    if projects < 1:
        missing.append("project")
    if assessments < 1:
        missing.append("saved assessment")
    if report_evidence < 1:
        missing.append("report profile/approval/delivery evidence")
    if monitoring_jobs < 1:
        missing.append("monitoring history")

    if missing:
        raise RecoveryReadinessError(
            "Restored snapshot is structurally valid but is not sufficient for #296 "
            "recovery readiness; missing representative " + ", ".join(missing) + "."
        )

    return RecoveryReadinessSummary(
        users=users,
        tenants=tenants,
        projects=projects,
        assessments=assessments,
        report_evidence=report_evidence,
        monitoring_jobs=monitoring_jobs,
    )
