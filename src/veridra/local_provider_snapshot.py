from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from .stripe_billing import StripeCheckoutReservationStore, StripeTenantBindingStore
from .workspace_policy import WorkspaceStore


class LocalProviderSnapshotError(RuntimeError):
    pass


def _tenant_id(value: str) -> str:
    checked = value.strip().lower()
    if len(checked) != 24 or any(char not in "0123456789abcdef" for char in checked):
        raise LocalProviderSnapshotError("Tenant identifier must be 24 lowercase hex characters.")
    return checked


def build_local_provider_snapshot(
    *,
    tenant_root: Path,
    tenant_id: str,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    checked_id = _tenant_id(tenant_id)
    root = tenant_root.expanduser().resolve()
    workspace_store = WorkspaceStore(root / checked_id / "workspace")
    if not workspace_store.path.exists():
        raise LocalProviderSnapshotError("Tenant workspace was not found.")
    workspace = workspace_store.load()
    binding = StripeTenantBindingStore(root).load(checked_id)
    reservation = StripeCheckoutReservationStore(root).load(checked_id)

    return {
        "contract": "veridra_local_provider_state_snapshot",
        "version": "1.0",
        "captured_at": (captured_at or datetime.now(UTC)).astimezone(UTC).isoformat(),
        "tenant_id": checked_id,
        "workspace": {
            "plan": workspace.plan.value,
            "status": workspace.status.value,
            "cycle_anchor_day": workspace.cycle_anchor_day,
        },
        "stripe": {
            "bound": binding is not None,
            "customer_id": binding.customer_id if binding is not None else None,
            "subscription_id": binding.subscription_id if binding is not None else None,
            "binding_updated_at": (
                binding.updated_at.astimezone(UTC).isoformat()
                if binding is not None
                else None
            ),
            "checkout_reservation": (
                {
                    "plan": reservation.plan.value,
                    "created_at": reservation.created_at.astimezone(UTC).isoformat(),
                    "expires_at": reservation.expires_at.astimezone(UTC).isoformat(),
                }
                if reservation is not None
                else None
            ),
        },
        "secrets_included": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Capture a secret-free read-only snapshot of local commercial workspace "
            "and Stripe binding state."
        )
    )
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--tenant-data-root", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    return parser


def main() -> None:
    args = _parser().parse_args()
    configured = args.tenant_data_root or os.environ.get("VERIDRA_TENANT_DATA_ROOT")
    if configured is None:
        raise SystemExit(
            "Tenant data root is required via --tenant-data-root or VERIDRA_TENANT_DATA_ROOT."
        )
    try:
        payload = build_local_provider_snapshot(
            tenant_root=Path(configured),
            tenant_id=args.tenant_id,
        )
    except LocalProviderSnapshotError as exc:
        raise SystemExit(f"status=failed error={exc}") from exc

    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
