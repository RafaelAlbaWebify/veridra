from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from veridra.recovery_readiness import (
    RecoveryReadinessError,
    validate_recovery_readiness,
)


def _identity(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE users (id TEXT PRIMARY KEY)")
        connection.execute("CREATE TABLE tenants (id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO users VALUES ('user-1')")
        connection.execute("INSERT INTO tenants VALUES ('tenant-1')")
        connection.commit()


def _monitoring(path: Path, *, jobs: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE monitoring_jobs (id TEXT PRIMARY KEY)")
        for index in range(jobs):
            connection.execute(
                "INSERT INTO monitoring_jobs VALUES (?)",
                (f"job-{index}",),
            )
        connection.commit()


def _representative_state(root: Path) -> tuple[Path, Path]:
    identity = root / "identity" / "veridra.sqlite3"
    tenants = root / "tenants"
    _identity(identity)
    tenant = tenants / ("a" * 24)
    project_id = "b" * 24
    assessment_id = "c" * 24

    project = tenant / "projects" / f"{project_id}.json"
    project.parent.mkdir(parents=True, exist_ok=True)
    project.write_text('{"name":"Recovered project"}', encoding="utf-8")

    assessment = (
        tenant
        / "projects"
        / project_id
        / "assessments"
        / f"{assessment_id}.json"
    )
    assessment.parent.mkdir(parents=True, exist_ok=True)
    assessment.write_text('{"assessment":"evidence"}', encoding="utf-8")

    profile = tenant / "report-profiles" / ("d" * 24 + ".json")
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text('{"organisation_name":"Webify"}', encoding="utf-8")

    _monitoring(tenants / "monitoring-jobs.sqlite3")
    return identity, tenants


def test_recovery_readiness_accepts_representative_restored_state(
    tmp_path: Path,
) -> None:
    identity, tenants = _representative_state(tmp_path)

    summary = validate_recovery_readiness(
        identity_database=identity,
        tenant_data_root=tenants,
    )

    assert summary.users == 1
    assert summary.tenants == 1
    assert summary.projects == 1
    assert summary.assessments == 1
    assert summary.report_evidence == 1
    assert summary.monitoring_jobs == 1


@pytest.mark.parametrize(
    "missing",
    ("project", "assessment", "report", "monitoring"),
)
def test_recovery_readiness_rejects_structurally_valid_but_incomplete_state(
    tmp_path: Path,
    missing: str,
) -> None:
    identity, tenants = _representative_state(tmp_path)
    tenant = tenants / ("a" * 24)
    project_id = "b" * 24

    if missing == "project":
        (tenant / "projects" / f"{project_id}.json").unlink()
    elif missing == "assessment":
        for path in (tenant / "projects" / project_id / "assessments").glob("*.json"):
            path.unlink()
    elif missing == "report":
        for path in (tenant / "report-profiles").glob("*.json"):
            path.unlink()
    else:
        (tenants / "monitoring-jobs.sqlite3").unlink()
        _monitoring(tenants / "monitoring-jobs.sqlite3", jobs=0)

    with pytest.raises(RecoveryReadinessError, match="recovery readiness"):
        validate_recovery_readiness(
            identity_database=identity,
            tenant_data_root=tenants,
        )
