from __future__ import annotations

import json
from pathlib import Path

import pytest

from veridra.project_migration_cli import main
from veridra.project_store import ClientProject, ProjectStore
from veridra.tenant_migration import MigrationStatus, TenantMigrationManifest

TENANT_ID = "b" * 24


def _plan(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    source = tmp_path / "legacy"
    target = tmp_path / "tenants"
    manifest = tmp_path / "migration" / "manifest.json"
    project_id = ProjectStore(source).save(
        ClientProject.build(name="Legacy", target_url="https://example.com")
    )
    main(
        [
            "plan",
            "--source",
            str(source),
            "--tenant",
            TENANT_ID,
            "--manifest",
            str(manifest),
        ]
    )
    return source, target, manifest, project_id


def test_plan_writes_planned_manifest_without_changing_source(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    manifest_path = tmp_path / "manifest.json"
    project_id = ProjectStore(source).save(
        ClientProject.build(name="Legacy", target_url="https://example.com")
    )
    source_path = source / f"{project_id}.json"
    before = source_path.read_bytes()

    main(
        [
            "plan",
            "--source",
            str(source),
            "--tenant",
            TENANT_ID,
            "--manifest",
            str(manifest_path),
        ]
    )

    manifest = TenantMigrationManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    assert manifest.status == MigrationStatus.planned
    assert manifest.target_tenant_id == TENANT_ID
    assert source_path.read_bytes() == before


def test_apply_requires_exact_tenant_confirmation(tmp_path: Path) -> None:
    source, target, manifest, _ = _plan(tmp_path)
    evidence = tmp_path / "evidence.json"

    with pytest.raises(SystemExit, match="Exact --confirm-tenant"):
        main(
            [
                "apply",
                "--source",
                str(source),
                "--target-root",
                str(target),
                "--manifest",
                str(manifest),
                "--evidence",
                str(evidence),
                "--confirm-tenant",
                "c" * 24,
            ]
        )

    assert not evidence.exists()


def test_apply_and_rollback_persist_manifest_and_evidence(tmp_path: Path) -> None:
    source, target, manifest_path, project_id = _plan(tmp_path)
    evidence_path = tmp_path / "migration" / "evidence.json"

    main(
        [
            "apply",
            "--source",
            str(source),
            "--target-root",
            str(target),
            "--manifest",
            str(manifest_path),
            "--evidence",
            str(evidence_path),
            "--confirm-tenant",
            TENANT_ID,
        ]
    )

    applied = TenantMigrationManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    target_path = target / TENANT_ID / "projects" / f"{project_id}.json"
    assert applied.status == MigrationStatus.applied
    assert evidence["created_target_ids"] == [project_id]
    assert target_path.exists()
    assert (source / f"{project_id}.json").exists()

    main(
        [
            "rollback",
            "--source",
            str(source),
            "--target-root",
            str(target),
            "--manifest",
            str(manifest_path),
            "--evidence",
            str(evidence_path),
            "--confirm-tenant",
            TENANT_ID,
        ]
    )

    rolled_back = TenantMigrationManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    assert rolled_back.status == MigrationStatus.rolled_back
    assert not target_path.exists()
    assert (source / f"{project_id}.json").exists()
