from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from .stripe_billing import (
    StripeApiClient,
    StripeBillingConfig,
    StripeBillingError,
    StripeTenantBindingStore,
)
from .workspace_policy import PlanName, WorkspaceStatus, WorkspaceStore


class LocalH6Phase4Error(RuntimeError):
    pass


def _tenant_id(value: str) -> str:
    checked = value.strip().lower()
    if len(checked) != 24 or any(char not in "0123456789abcdef" for char in checked):
        raise LocalH6Phase4Error(
            "Tenant identifier must be 24 lowercase hexadecimal characters."
        )
    return checked


def _wait_for(
    *,
    client: StripeApiClient,
    subscription_id: str,
    tenant_root: Path,
    tenant_id: str,
    provider_status: str,
    workspace_status: WorkspaceStatus,
    timeout_seconds: float,
) -> tuple[str, str]:
    deadline = time.monotonic() + timeout_seconds
    last_provider = ""
    last_workspace = ""
    while time.monotonic() < deadline:
        current = client.retrieve_subscription(subscription_id)
        workspace = WorkspaceStore(tenant_root / tenant_id / "workspace").load()
        last_provider = current.status
        last_workspace = workspace.status.value
        if (
            current.status == provider_status
            and workspace.status is workspace_status
        ):
            return last_provider, last_workspace
        time.sleep(0.5)
    raise LocalH6Phase4Error(
        "Timed out waiting for provider/workspace state "
        f"{provider_status}/{workspace_status.value}; "
        f"last_state={last_provider}/{last_workspace}"
    )


def run_phase4(
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
        raise LocalH6Phase4Error("Tenant workspace was not found.")

    binding = StripeTenantBindingStore(root).load(checked)
    if binding is None:
        raise LocalH6Phase4Error("Tenant has no Stripe subscription binding.")

    stripe = client or StripeApiClient(config)
    before = stripe.retrieve_subscription(binding.subscription_id)
    workspace_before = workspace_store.load()
    if (
        before.status != "active"
        or workspace_before.status is not WorkspaceStatus.active
        or workspace_before.plan is not PlanName.solo
    ):
        raise LocalH6Phase4Error(
            "Phase 4 automation expects the H6 tenant to start Solo/active."
        )

    original_payment_method = before.default_payment_method

    failing_payment_method = stripe.attach_payment_method(
        payment_method_id="pm_card_chargeCustomerFail",
        customer_id=binding.customer_id,
    )
    requested_failure = stripe.update_subscription_payment_method(
        subscription_id=binding.subscription_id,
        payment_method_id=failing_payment_method,
        reset_billing_cycle=True,
        payment_behavior="allow_incomplete",
    )

    provider_failed, workspace_failed = _wait_for(
        client=stripe,
        subscription_id=binding.subscription_id,
        tenant_root=root,
        tenant_id=checked,
        provider_status="past_due",
        workspace_status=WorkspaceStatus.suspended,
        timeout_seconds=timeout_seconds,
    )
    failed_current = stripe.retrieve_subscription(binding.subscription_id)
    if not failed_current.latest_invoice:
        raise LocalH6Phase4Error(
            "Stripe past_due subscription did not expose a latest invoice."
        )

    recovery_payment_method = stripe.attach_payment_method(
        payment_method_id="pm_card_visa",
        customer_id=binding.customer_id,
    )
    stripe.update_subscription_payment_method(
        subscription_id=binding.subscription_id,
        payment_method_id=recovery_payment_method,
        reset_billing_cycle=False,
        payment_behavior="allow_incomplete",
    )
    stripe.pay_invoice(failed_current.latest_invoice)

    provider_recovered, workspace_recovered = _wait_for(
        client=stripe,
        subscription_id=binding.subscription_id,
        tenant_root=root,
        tenant_id=checked,
        provider_status="active",
        workspace_status=WorkspaceStatus.active,
        timeout_seconds=timeout_seconds,
    )

    restored_original_payment_method = False
    if original_payment_method:
        stripe.update_subscription_payment_method(
            subscription_id=binding.subscription_id,
            payment_method_id=original_payment_method,
            reset_billing_cycle=False,
            payment_behavior="allow_incomplete",
        )
        restored_original_payment_method = True

    final_subscription = stripe.retrieve_subscription(binding.subscription_id)
    final_workspace = workspace_store.load()
    if (
        final_subscription.status != "active"
        or final_workspace.status is not WorkspaceStatus.active
        or final_workspace.plan is not PlanName.solo
    ):
        raise LocalH6Phase4Error("Phase 4 cleanup did not leave the tenant Solo/active.")

    return {
        "contract": "veridra_local_commercial_h6_phase4",
        "version": "1.0",
        "tenant_id": checked,
        "subscription_id": binding.subscription_id,
        "customer_id": binding.customer_id,
        "started_at": datetime.now(UTC).isoformat(),
        "failure": {
            "requested_subscription_status": requested_failure.status,
            "provider_status": provider_failed,
            "workspace_status": workspace_failed,
            "latest_invoice_present": True,
            "pass": True,
        },
        "recovery": {
            "provider_status": provider_recovered,
            "workspace_status": workspace_recovered,
            "original_payment_method_restored": restored_original_payment_method,
            "pass": True,
        },
        "final_state": {
            "provider_status": final_subscription.status,
            "workspace_plan": final_workspace.plan.value,
            "workspace_status": final_workspace.status.value,
        },
        "pass": True,
        "secrets_included": False,
        "finished_at": datetime.now(UTC).isoformat(),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Automate local-commercial H6 Phase 4 against real Stripe test mode: "
            "payment failure -> past_due/suspended -> payment recovery -> active."
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
        evidence = run_phase4(
            tenant_root=Path(configured_root),
            tenant_id=args.tenant_id,
            config=config,
            timeout_seconds=args.timeout_seconds,
        )
    except (LocalH6Phase4Error, StripeBillingError, OSError, ValueError) as exc:
        raise SystemExit(f"status=failed error={exc}") from exc

    rendered = json.dumps(evidence, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
