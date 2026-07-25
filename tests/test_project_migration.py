from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_migration import (
    ProjectMigrationError,
    ProjectMigrationExecutor,
    plan_project_records,
    project_source_fingerprint,
)
from veridra.project_store import ClientProject, ProjectStore
from veridra.tenant_migration import (
    TenantMigrationManifest,
    confirm_manifest,
)

NOW = datetime(2026, 7, 24, 18, 0, tzinfo=UTC)
TENANT_ID = "b" * 24


def _identity(role: TenantRole = TenantRole.owner) -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id=TENANT_ID,
        membership_role=role,
        session_id="session-project-migration-001",
        authenticated_at=NOW,
    )


def _confirmed_manifest(source: Path) -> TenantMigrationManifest:
    records = plan_project_records(source_directory=source)
    manifest = TenantMigrationManifest.build(
        target_tenant_id=TENANT_ID,
        source_root_fingerprint=project_source_fingerprint(source),
        records=records,
        now=NOW,
    )
    return confirm_manifest(
        manifest,
        confirmed_target_tenant_id=TENANT_ID,
        now=NOW,
    )


def test_planning_is_read_only_and_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    store = ProjectStore(source)
    project_id = store.save(ClientProject.build(name="Legacy", target_url="https://example.com"))
    source_path = source / f"{project_id}.json"
    before = source_path.read_bytes()

    first = plan_project_records(source_directory=source)
    second = plan_project_records(source_directory=source)

    assert first == second
    assert source_path.read_bytes() == before
    assert [path.name for path in source.glob("*.json")] == [f"{project_id}.json"]


def test_source_fingerprint_tracks_json_inventory_only(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    store = ProjectStore(source)
    first_id = store.save(ClientProject.build(name="First", target_url="https://one.example"))
    first = project_source_fingerprint(source)

    (source / "notes.txt").write_text("ignored", encoding="utf-8")
    assert project_source_fingerprint(source) == first

    second_id = store.save(ClientProject.build(name="Second", target_url="https://two.example"))
    second = project_source_fingerprint(source)
    assert second != first

    (source / f"{first_id}.json").write_text("{}", encoding="utf-8")
    modified = project_source_fingerprint(source)
    assert modified != second

    (source / f"{second_id}.json").unlink()
    assert project_source_fingerprint(source) != modified


def test_apply_copies_and_verifies_without_deleting_source(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    target = tmp_path / "tenants"
    legacy_store = ProjectStore(source)
    project_id = legacy_store.save(
        ClientProject.build(name="Legacy", target_url="https://example.com")
    )
    manifest = _confirmed_manifest(source)
    executor = ProjectMigrationExecutor(source_directory=source, target_root=target)

    result = executor.apply(identity=_identity(), manifest=manifest)

    source_path = source / f"{project_id}.json"
    target_path = target / TENANT_ID / "projects" / f"{project_id}.json"
    assert source_path.exists()
    assert target_path.read_bytes() == source_path.read_bytes()
    assert result.evidence.created_target_ids == (project_id,)
    assert result.evidence.reused_target_ids == ()
    assert (
        result.evidence.source_checksums[source_path.name]
        == result.evidence.target_checksums[project_id]
    )
    assert result.manifest.status.value == "applied"


def test_apply_reuses_identical_existing_target(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    target = tmp_path / "tenants"
    project = ClientProject.build(name="Existing", target_url="https://example.com")
    project_id = ProjectStore(source).save(project)
    target_store = ProjectStore(target / TENANT_ID / "projects")
    assert target_store.save(project) == project_id
    manifest = _confirmed_manifest(source)

    result = ProjectMigrationExecutor(source_directory=source, target_root=target).apply(
        identity=_identity(),
        manifest=manifest,
    )

    assert result.evidence.created_target_ids == ()
    assert result.evidence.reused_target_ids == (project_id,)


def test_apply_rejects_changed_inventory_and_conflicting_target(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    target = tmp_path / "tenants"
    project = ClientProject.build(name="Legacy", target_url="https://example.com")
    project_id = ProjectStore(source).save(project)
    manifest = _confirmed_manifest(source)
    source_path = source / f"{project_id}.json"
    source_path.write_text("{}", encoding="utf-8")

    executor = ProjectMigrationExecutor(source_directory=source, target_root=target)
    with pytest.raises(ProjectMigrationError, match="inventory changed"):
        executor.apply(identity=_identity(), manifest=manifest)

    ProjectStore(source).save(project)
    target_path = target / TENANT_ID / "projects" / f"{project_id}.json"
    target_path.parent.mkdir(parents=True)
    target_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ProjectMigrationError, match="collision"):
        executor.apply(identity=_identity(), manifest=manifest)


def test_apply_rejects_added_or_removed_json_before_writing(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    target = tmp_path / "tenants"
    store = ProjectStore(source)
    first_id = store.save(ClientProject.build(name="First", target_url="https://one.example"))
    manifest = _confirmed_manifest(source)
    second_id = store.save(ClientProject.build(name="Second", target_url="https://two.example"))
    executor = ProjectMigrationExecutor(source_directory=source, target_root=target)

    with pytest.raises(ProjectMigrationError, match="inventory changed"):
        executor.apply(identity=_identity(), manifest=manifest)
    assert not (target / TENANT_ID / "projects").exists()

    (source / f"{second_id}.json").unlink()
    (source / f"{first_id}.json").unlink()
    with pytest.raises(ProjectMigrationError, match="inventory changed"):
        executor.apply(identity=_identity(), manifest=manifest)
    assert not (target / TENANT_ID / "projects").exists()


def test_rollback_removes_only_created_unchanged_targets(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    target = tmp_path / "tenants"
    project_id = ProjectStore(source).save(
        ClientProject.build(name="Legacy", target_url="https://example.com")
    )
    executor = ProjectMigrationExecutor(source_directory=source, target_root=target)
    result = executor.apply(identity=_identity(), manifest=_confirmed_manifest(source))

    rolled_back = executor.rollback(
        identity=_identity(),
        manifest=result.manifest,
        evidence=result.evidence,
    )

    assert rolled_back.status.value == "rolled_back"
    assert not (target / TENANT_ID / "projects" / f"{project_id}.json").exists()
    assert (source / f"{project_id}.json").exists()


def test_rollback_refuses_to_delete_modified_target(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    target = tmp_path / "tenants"
    project_id = ProjectStore(source).save(
        ClientProject.build(name="Legacy", target_url="https://example.com")
    )
    executor = ProjectMigrationExecutor(source_directory=source, target_root=target)
    result = executor.apply(identity=_identity(), manifest=_confirmed_manifest(source))
    target_path = target / TENANT_ID / "projects" / f"{project_id}.json"
    target_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ProjectMigrationError, match="changed after migration"):
        executor.rollback(
            identity=_identity(),
            manifest=result.manifest,
            evidence=result.evidence,
        )
    assert target_path.exists()
