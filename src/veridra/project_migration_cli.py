from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

from .identity_tenancy import RequestIdentity, TenantRole
from .project_migration import (
    ProjectMigrationEvidence,
    ProjectMigrationExecutor,
    plan_project_records,
)
from .tenant_migration import (
    TenantMigrationManifest,
    confirm_manifest,
)

_OPERATOR_USER_ID = "0" * 24
_OPERATOR_SESSION_ID = "offline-project-migration"


def _fail(message: str) -> NoReturn:
    raise SystemExit(message)


def _fingerprint(path: Path) -> str:
    return hashlib.sha256(str(path.expanduser().resolve()).encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _read_manifest(path: Path) -> TenantMigrationManifest:
    return TenantMigrationManifest.model_validate_json(path.read_text(encoding="utf-8"))


def _read_evidence(path: Path) -> ProjectMigrationEvidence:
    return ProjectMigrationEvidence.model_validate_json(path.read_text(encoding="utf-8"))


def _operator_identity(tenant_id: str) -> RequestIdentity:
    """Build a local offline authority marker, not a web-authenticated identity."""
    return RequestIdentity(
        user_id=_OPERATOR_USER_ID,
        tenant_id=tenant_id,
        membership_role=TenantRole.owner,
        session_id=_OPERATOR_SESSION_ID,
        authenticated_at=datetime.now(UTC),
    )


def _require_confirmation(expected: str, supplied: str | None) -> None:
    if supplied != expected:
        _fail("Exact --confirm-tenant value is required and must match the manifest target.")


def _plan(args: argparse.Namespace) -> None:
    source = Path(args.source)
    manifest_path = Path(args.manifest)
    records = plan_project_records(source_directory=source)
    if not records:
        _fail("No valid legacy project JSON records were found.")
    manifest = TenantMigrationManifest.build(
        target_tenant_id=args.tenant,
        source_root_fingerprint=_fingerprint(source),
        records=records,
    )
    _write_json(manifest_path, manifest.model_dump(mode="json"))
    print(f"Planned {len(records)} project record(s) for tenant {args.tenant}.")
    print(f"Manifest: {manifest_path}")


def _apply(args: argparse.Namespace) -> None:
    manifest_path = Path(args.manifest)
    evidence_path = Path(args.evidence)
    manifest = _read_manifest(manifest_path)
    _require_confirmation(manifest.target_tenant_id, args.confirm_tenant)
    confirmed = confirm_manifest(
        manifest,
        confirmed_target_tenant_id=args.confirm_tenant,
    )
    executor = ProjectMigrationExecutor(
        source_directory=Path(args.source),
        target_root=Path(args.target_root),
    )
    result = executor.apply(
        identity=_operator_identity(manifest.target_tenant_id),
        manifest=confirmed,
    )
    _write_json(manifest_path, result.manifest.model_dump(mode="json"))
    _write_json(evidence_path, result.evidence.model_dump(mode="json"))
    print(f"Applied migration {result.manifest.id}.")
    print(f"Created: {len(result.evidence.created_target_ids)}")
    print(f"Reused: {len(result.evidence.reused_target_ids)}")


def _rollback(args: argparse.Namespace) -> None:
    manifest_path = Path(args.manifest)
    evidence_path = Path(args.evidence)
    manifest = _read_manifest(manifest_path)
    evidence = _read_evidence(evidence_path)
    _require_confirmation(manifest.target_tenant_id, args.confirm_tenant)
    executor = ProjectMigrationExecutor(
        source_directory=Path(args.source),
        target_root=Path(args.target_root),
    )
    rolled_back = executor.rollback(
        identity=_operator_identity(manifest.target_tenant_id),
        manifest=manifest,
        evidence=evidence,
    )
    _write_json(manifest_path, rolled_back.model_dump(mode="json"))
    print(f"Rolled back migration {rolled_back.id}.")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="veridra-project-migrate",
        description=(
            "Offline operator tool for explicitly planning, applying, and rolling back "
            "legacy project migration into one tenant. This is not web authentication."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan")
    plan.add_argument("--source", required=True)
    plan.add_argument("--tenant", required=True)
    plan.add_argument("--manifest", required=True)
    plan.set_defaults(handler=_plan)

    apply = subparsers.add_parser("apply")
    apply.add_argument("--source", required=True)
    apply.add_argument("--target-root", required=True)
    apply.add_argument("--manifest", required=True)
    apply.add_argument("--evidence", required=True)
    apply.add_argument("--confirm-tenant", required=True)
    apply.set_defaults(handler=_apply)

    rollback = subparsers.add_parser("rollback")
    rollback.add_argument("--source", required=True)
    rollback.add_argument("--target-root", required=True)
    rollback.add_argument("--manifest", required=True)
    rollback.add_argument("--evidence", required=True)
    rollback.add_argument("--confirm-tenant", required=True)
    rollback.set_defaults(handler=_rollback)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    args.handler(args)


if __name__ == "__main__":
    main()
