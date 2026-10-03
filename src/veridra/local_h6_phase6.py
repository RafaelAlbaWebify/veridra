from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .backup_restore import create_backup, restore_backup
from .local_provider_reconcile import reconcile_local_provider
from .local_provider_snapshot import build_local_provider_snapshot
from .stripe_billing import StripeBillingConfig
from .subscription_authority import (
    SubscriptionAuthority,
    SubscriptionAuthorityError,
    SubscriptionUpdate,
)
from .workspace_policy import PlanName, WorkspaceStatus, WorkspaceStore


class LocalH6Phase6Error(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_phase6(
    *,
    identity_database: Path,
    tenant_root: Path,
    tenant_id: str,
    backup_path: Path,
    recovery_root: Path,
    config: StripeBillingConfig,
) -> dict[str, object]:
    backup = create_backup(
        identity_database=identity_database,
        tenant_data_root=tenant_root,
        output=backup_path,
        confirm_quiesced=True,
    )
    archive_hash = _sha256(backup.archive)

    if recovery_root.exists():
        shutil.rmtree(recovery_root)
    restored_identity = recovery_root / "identity" / "veridra.sqlite3"
    restored_tenants = recovery_root / "tenants"
    restore = restore_backup(
        archive=backup.archive,
        identity_database=restored_identity,
        tenant_data_root=restored_tenants,
        confirm_quiesced=True,
    )

    initial_snapshot = build_local_provider_snapshot(
        tenant_root=restored_tenants,
        tenant_id=tenant_id,
    )
    initial_reconcile = reconcile_local_provider(
        tenant_root=restored_tenants,
        tenant_id=tenant_id,
        apply=False,
        config=config,
    )
    if initial_reconcile["drift"]:
        raise LocalH6Phase6Error("Fresh isolated restore already drifted from Stripe.")

    workspace_store = WorkspaceStore(restored_tenants / tenant_id / "workspace")
    before_drift = workspace_store.load()
    workspace_store.save(before_drift.model_copy(update={"plan": PlanName.professional}))

    read_only = reconcile_local_provider(
        tenant_root=restored_tenants,
        tenant_id=tenant_id,
        apply=False,
        config=config,
    )
    if not read_only["drift"] or read_only["applied"]:
        raise LocalH6Phase6Error("Read-only reconciliation did not detect drift safely.")

    applied = reconcile_local_provider(
        tenant_root=restored_tenants,
        tenant_id=tenant_id,
        apply=True,
        config=config,
    )
    if not applied["drift"] or not applied["applied"]:
        raise LocalH6Phase6Error("Authoritative reconciliation did not repair drift.")

    authority = SubscriptionAuthority(restored_tenants)
    events = authority.list_events(tenant_id)
    if not events:
        raise LocalH6Phase6Error("Restored tenant has no subscription event evidence.")
    latest = events[-1].update

    replay = authority.apply(latest)
    if replay.applied:
        raise LocalH6Phase6Error("Replayed provider event unexpectedly reapplied.")

    stale = SubscriptionUpdate(
        tenant_id=tenant_id,
        provider="stripe",
        provider_event_id="h6-phase6-stale-proof",
        external_subscription_id=latest.external_subscription_id,
        plan=PlanName.professional,
        status=WorkspaceStatus.suspended,
        cycle_anchor_day=latest.cycle_anchor_day,
        occurred_at=latest.occurred_at - timedelta(seconds=1),
    )
    stale_rejected = False
    try:
        authority.apply(stale)
    except SubscriptionAuthorityError as exc:
        stale_rejected = "Stale subscription event" in str(exc)
    if not stale_rejected:
        raise LocalH6Phase6Error("Stale provider event was not rejected.")

    final_snapshot = build_local_provider_snapshot(
        tenant_root=restored_tenants,
        tenant_id=tenant_id,
    )
    return {
        "contract": "veridra_local_commercial_h6_phase6",
        "version": "1.0",
        "tenant_id": tenant_id,
        "backup": {
            "archive": str(backup.archive),
            "sha256": archive_hash,
            "files": len(backup.manifest.files),
            "consistency": backup.manifest.consistency,
        },
        "restore": {
            "root": str(recovery_root),
            "restored_files": restore.restored_files,
            "initial_snapshot": initial_snapshot,
        },
        "reconciliation": {
            "initial_read_only": initial_reconcile,
            "intentional_drift_read_only": read_only,
            "apply": applied,
        },
        "event_safety": {
            "replay_applied": replay.applied,
            "stale_rejected": stale_rejected,
            "latest_provider_event_id": latest.provider_event_id,
            "pass": True,
        },
        "final_snapshot": final_snapshot,
        "pass": True,
        "secrets_included": False,
        "finished_at": datetime.now(UTC).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--identity-db", type=Path, required=True)
    parser.add_argument("--tenant-data-root", type=Path, required=True)
    parser.add_argument("--backup-path", type=Path, required=True)
    parser.add_argument("--recovery-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    config = StripeBillingConfig.from_environment()
    if config is None:
        raise SystemExit("status=failed error=Stripe billing configuration is unavailable.")

    try:
        evidence = run_phase6(
            identity_database=args.identity_db,
            tenant_root=args.tenant_data_root,
            tenant_id=args.tenant_id,
            backup_path=args.backup_path,
            recovery_root=args.recovery_root,
            config=config,
        )
    except Exception as exc:
        raise SystemExit(f"status=failed error={exc}") from exc

    rendered = json.dumps(evidence, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
