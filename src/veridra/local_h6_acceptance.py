from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from .stripe_billing import (
    StripeApiClient,
    StripeBillingConfig,
    StripeBillingError,
    StripeTenantBindingStore,
)
from .workspace_policy import PlanName, WorkspaceStatus, WorkspaceStore


class LocalH6AcceptanceError(RuntimeError):
    pass


def _tenant_id(value: str) -> str:
    checked = value.strip().lower()
    if len(checked) != 24 or any(char not in "0123456789abcdef" for char in checked):
        raise LocalH6AcceptanceError(
            "Tenant identifier must be 24 lowercase hexadecimal characters."
        )
    return checked


def _snapshot(*, tenant_root: Path, tenant_id: str) -> dict[str, object]:
    workspace = WorkspaceStore(tenant_root / tenant_id / "workspace").load()
    binding = StripeTenantBindingStore(tenant_root).load(tenant_id)
    return {
        "captured_at": datetime.now(UTC).isoformat(),
        "workspace": {
            "plan": workspace.plan.value,
            "status": workspace.status.value,
            "cycle_anchor_day": workspace.cycle_anchor_day,
        },
        "stripe": {
            "bound": binding is not None,
            "customer_id": binding.customer_id if binding is not None else None,
            "subscription_id": binding.subscription_id if binding is not None else None,
        },
    }


def _wait_for_workspace(
    *,
    tenant_root: Path,
    tenant_id: str,
    plan: PlanName,
    status: WorkspaceStatus,
    timeout_seconds: float,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    last = _snapshot(tenant_root=tenant_root, tenant_id=tenant_id)
    while time.monotonic() < deadline:
        workspace = last["workspace"]
        if (
            isinstance(workspace, dict)
            and workspace.get("plan") == plan.value
            and workspace.get("status") == status.value
        ):
            return last
        time.sleep(0.5)
        last = _snapshot(tenant_root=tenant_root, tenant_id=tenant_id)
    raise LocalH6AcceptanceError(
        f"Timed out waiting for webhook projection to {plan.value}/{status.value}; "
        f"last_state={last['workspace']}"
    )


def run_phase3(
    *,
    tenant_root: Path,
    tenant_id: str,
    config: StripeBillingConfig,
    timeout_seconds: float = 30.0,
    client: StripeApiClient | None = None,
) -> dict[str, object]:
    checked = _tenant_id(tenant_id)
    root = tenant_root.expanduser().resolve()
    workspace_store = WorkspaceStore(root / checked / "workspace")
    if not workspace_store.path.exists():
        raise LocalH6AcceptanceError("Tenant workspace was not found.")

    binding = StripeTenantBindingStore(root).load(checked)
    if binding is None:
        raise LocalH6AcceptanceError("Tenant has no Stripe subscription binding.")

    stripe = client or StripeApiClient(config)
    before = _snapshot(tenant_root=root, tenant_id=checked)
    workspace = workspace_store.load()
    if workspace.plan is not PlanName.solo or workspace.status is not WorkspaceStatus.active:
        raise LocalH6AcceptanceError(
            "Phase 3 automation expects the bound H6 tenant to start Solo/active."
        )

    try:
        portal = stripe.create_portal(customer_id=binding.customer_id)
    except StripeBillingError as exc:
        raise LocalH6AcceptanceError("Stripe Billing Portal session could not be created.") from exc
    parsed = urlparse(portal.url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "billing.stripe.com"
        or parsed.username
        or parsed.password
    ):
        raise LocalH6AcceptanceError("Stripe Billing Portal returned an unexpected URL.")

    transitions: list[dict[str, object]] = []
    for target in (PlanName.professional, PlanName.solo):
        provider_before = stripe.retrieve_subscription(binding.subscription_id)
        try:
            requested = stripe.update_subscription_plan(
                subscription_id=binding.subscription_id,
                plan=target,
            )
        except StripeBillingError as exc:
            raise LocalH6AcceptanceError(
                f"Stripe plan transition to {target.value} failed."
            ) from exc
        projected = _wait_for_workspace(
            tenant_root=root,
            tenant_id=checked,
            plan=target,
            status=WorkspaceStatus.active,
            timeout_seconds=timeout_seconds,
        )
        provider_after = stripe.retrieve_subscription(binding.subscription_id)
        mapped_prices = [item.price.id for item in provider_after.items.data]
        expected_price = config.price_for_plan(target)
        if mapped_prices != [expected_price]:
            raise LocalH6AcceptanceError(
                f"Stripe provider state did not settle on {target.value}."
            )
        transitions.append(
            {
                "target_plan": target.value,
                "provider_status_before": provider_before.status,
                "provider_status_after_request": requested.status,
                "provider_status_after_webhook": provider_after.status,
                "provider_price_after": expected_price,
                "projected_workspace": projected["workspace"],
                "pass": True,
            }
        )

    after = _snapshot(tenant_root=root, tenant_id=checked)
    return {
        "contract": "veridra_local_commercial_h6_phase3",
        "version": "1.0",
        "started_from": before,
        "tenant_id": checked,
        "portal": {
            "session_id": portal.id,
            "host": parsed.hostname,
            "pass": True,
        },
        "transitions": transitions,
        "finished_at": datetime.now(UTC).isoformat(),
        "final_state": after,
        "pass": True,
        "secrets_included": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Automate local-commercial H6 Phase 3 against real Stripe test mode. "
            "Requires the signed Stripe CLI listener to be forwarding subscription "
            "events to the local VERIDRA webhook."
        )
    )
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--tenant-data-root", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    return parser


def main() -> None:
    args = _parser().parse_args()
    configured_root = args.tenant_data_root or os.environ.get("VERIDRA_TENANT_DATA_ROOT")
    if configured_root is None:
        raise SystemExit("VERIDRA_TENANT_DATA_ROOT is required.")
    try:
        config = StripeBillingConfig.from_environment()
    except StripeBillingError as exc:
        raise SystemExit(f"status=failed error={exc}") from exc
    if config is None:
        raise SystemExit("status=failed error=Stripe billing configuration is unavailable.")
    try:
        evidence = run_phase3(
            tenant_root=Path(configured_root),
            tenant_id=args.tenant_id,
            config=config,
            timeout_seconds=args.timeout_seconds,
        )
    except (LocalH6AcceptanceError, StripeBillingError, OSError, ValueError) as exc:
        raise SystemExit(f"status=failed error={exc}") from exc

    rendered = json.dumps(evidence, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
