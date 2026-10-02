from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from .stripe_billing import (
    StripeApiClient,
    StripeBillingConfig,
    StripeBillingError,
    StripeReconciliationResult,
    StripeSubscriptionAdapter,
)


class LocalProviderReconciliationError(RuntimeError):
    pass


def _tenant_id(value: str) -> str:
    checked = value.strip().lower()
    if len(checked) != 24 or any(char not in "0123456789abcdef" for char in checked):
        raise LocalProviderReconciliationError(
            "Tenant identifier must be 24 lowercase hex characters."
        )
    return checked


def _evidence(
    result: StripeReconciliationResult,
    *,
    checked_at: datetime,
    apply_requested: bool,
) -> dict[str, object]:
    return {
        "contract": "veridra_local_provider_reconciliation",
        "version": "1.0",
        "checked_at": checked_at.astimezone(UTC).isoformat(),
        "tenant_id": result.tenant_id,
        "subscription_id": result.subscription_id,
        "customer_id": result.customer_id,
        "apply_requested": apply_requested,
        "drift": result.drift,
        "applied": result.applied,
        "workspace": {
            "plan": result.workspace_plan.value,
            "status": result.workspace_status.value,
            "cycle_anchor_day": result.workspace_cycle_anchor_day,
        },
        "provider": {
            "plan": result.provider_plan.value,
            "status": result.provider_status.value,
            "cycle_anchor_day": result.provider_cycle_anchor_day,
        },
        "secrets_included": False,
    }


def reconcile_local_provider(
    *,
    tenant_root: Path,
    tenant_id: str,
    apply: bool = False,
    checked_at: datetime | None = None,
    client: StripeApiClient | None = None,
    config: StripeBillingConfig | None = None,
) -> dict[str, object]:
    checked = _tenant_id(tenant_id)
    observed_at = (checked_at or datetime.now(UTC)).astimezone(UTC)
    resolved_config = config
    if resolved_config is None:
        try:
            resolved_config = StripeBillingConfig.from_environment()
        except StripeBillingError as exc:
            raise LocalProviderReconciliationError(str(exc)) from exc
    if resolved_config is None:
        raise LocalProviderReconciliationError(
            "Stripe billing configuration is not available."
        )
    resolved_client = client or StripeApiClient(resolved_config)
    adapter = StripeSubscriptionAdapter(
        config=resolved_config,
        tenant_root=tenant_root.expanduser().resolve(),
        client=resolved_client,
    )
    try:
        result = adapter.reconcile_tenant(
            checked,
            apply=apply,
            observed_at=observed_at,
        )
    except StripeBillingError as exc:
        raise LocalProviderReconciliationError(str(exc)) from exc
    return _evidence(
        result,
        checked_at=observed_at,
        apply_requested=apply,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare a local commercial VERIDRA tenant with the authoritative "
            "Stripe test subscription. Read-only unless --apply is supplied."
        )
    )
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--tenant-data-root", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Project authoritative Stripe plan/status into VERIDRA when drift exists.",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    configured = args.tenant_data_root or os.environ.get("VERIDRA_TENANT_DATA_ROOT")
    if configured is None:
        raise SystemExit(
            "Tenant data root is required via --tenant-data-root or "
            "VERIDRA_TENANT_DATA_ROOT."
        )
    try:
        payload = reconcile_local_provider(
            tenant_root=Path(configured),
            tenant_id=args.tenant_id,
            apply=args.apply,
        )
    except LocalProviderReconciliationError as exc:
        raise SystemExit(f"status=failed error={exc}") from exc

    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
