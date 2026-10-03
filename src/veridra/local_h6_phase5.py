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
    StripeSubscriptionAdapter,
    StripeTenantBindingStore,
    StripeWebhookEvent,
)
from .workspace_policy import PlanName, WorkspaceStatus, WorkspaceStore


class LocalH6Phase5Error(RuntimeError):
    pass


def _tenant_id(value: str) -> str:
    checked = value.strip().lower()
    if len(checked) != 24 or any(char not in "0123456789abcdef" for char in checked):
        raise LocalH6Phase5Error(
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
        if current.status == provider_status and workspace.status is workspace_status:
            return last_provider, last_workspace
        time.sleep(0.5)
    raise LocalH6Phase5Error(
        "Timed out waiting for provider/workspace state "
        f"{provider_status}/{workspace_status.value}; "
        f"last_state={last_provider}/{last_workspace}"
    )


def _wait_for_binding(
    *,
    tenant_root: Path,
    tenant_id: str,
    subscription_id: str,
    timeout_seconds: float,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    store = StripeTenantBindingStore(tenant_root)
    while time.monotonic() < deadline:
        binding = store.load(tenant_id)
        if binding is not None and binding.subscription_id == subscription_id:
            return
        time.sleep(0.5)
    raise LocalH6Phase5Error(
        "Timed out waiting for replacement subscription binding."
    )


def run_phase5(
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
        raise LocalH6Phase5Error("Tenant workspace was not found.")

    binding_store = StripeTenantBindingStore(root)
    binding = binding_store.load(checked)
    if binding is None:
        raise LocalH6Phase5Error("Tenant has no Stripe subscription binding.")

    stripe = client or StripeApiClient(config)
    before = stripe.retrieve_subscription(binding.subscription_id)
    workspace_before = workspace_store.load()
    if (
        before.status != "active"
        or workspace_before.status is not WorkspaceStatus.active
        or workspace_before.plan is not PlanName.solo
    ):
        raise LocalH6Phase5Error(
            "Phase 5 automation expects the H6 tenant to start Solo/active."
        )

    old_subscription_id = before.id
    customer_id = before.customer
    original_payment_method = before.default_payment_method

    canceled = stripe.cancel_subscription(old_subscription_id)

    provider_canceled, workspace_suspended = _wait_for(
        client=stripe,
        subscription_id=old_subscription_id,
        tenant_root=root,
        tenant_id=checked,
        provider_status="canceled",
        workspace_status=WorkspaceStatus.suspended,
        timeout_seconds=timeout_seconds,
    )

    replacement = stripe.create_subscription(
        tenant_id=checked,
        customer_id=customer_id,
        plan=PlanName.solo,
        default_payment_method=original_payment_method,
    )
    _wait_for_binding(
        tenant_root=root,
        tenant_id=checked,
        subscription_id=replacement.id,
        timeout_seconds=timeout_seconds,
    )
    provider_active, workspace_active = _wait_for(
        client=stripe,
        subscription_id=replacement.id,
        tenant_root=root,
        tenant_id=checked,
        provider_status="active",
        workspace_status=WorkspaceStatus.active,
        timeout_seconds=timeout_seconds,
    )

    current_binding = binding_store.load(checked)
    if current_binding is None or current_binding.subscription_id != replacement.id:
        raise LocalH6Phase5Error("Replacement subscription did not become current binding.")

    adapter = StripeSubscriptionAdapter(
        config=config,
        tenant_root=root,
        client=stripe,
    )
    replay = StripeWebhookEvent.model_validate(
        {
            "id": f"evt_h6_replay_{int(time.time())}",
            "type": "customer.subscription.deleted",
            "created": int(time.time()),
            "data": {
                "object": canceled.model_dump(mode="json"),
            },
        }
    )
    replay_result = adapter.handle(replay)
    if replay_result.applied:
        raise LocalH6Phase5Error(
            "Obsolete subscription deletion unexpectedly changed current tenant state."
        )
    after_replay = workspace_store.load()
    binding_after_replay = binding_store.load(checked)
    if (
        after_replay.status is not WorkspaceStatus.active
        or binding_after_replay is None
        or binding_after_replay.subscription_id != replacement.id
    ):
        raise LocalH6Phase5Error(
            "Obsolete subscription deletion disturbed the replacement binding."
        )

    return {
        "contract": "veridra_local_commercial_h6_phase5",
        "version": "1.0",
        "tenant_id": checked,
        "customer_id": customer_id,
        "old_subscription_id": old_subscription_id,
        "replacement_subscription_id": replacement.id,
        "cancellation": {
            "provider_status": provider_canceled,
            "workspace_status": workspace_suspended,
            "pass": True,
        },
        "replacement": {
            "provider_status": provider_active,
            "workspace_status": workspace_active,
            "binding_subscription_id": replacement.id,
            "pass": True,
        },
        "obsolete_deletion_guard": {
            "handled": replay_result.handled,
            "applied": replay_result.applied,
            "reason": replay_result.reason,
            "current_binding_preserved": True,
            "workspace_status": after_replay.status.value,
            "pass": True,
        },
        "final_state": {
            "provider_status": stripe.retrieve_subscription(replacement.id).status,
            "workspace_plan": after_replay.plan.value,
            "workspace_status": after_replay.status.value,
            "binding_subscription_id": replacement.id,
        },
        "pass": True,
        "secrets_included": False,
        "finished_at": datetime.now(UTC).isoformat(),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Automate local-commercial H6 Phase 5 against real Stripe test mode: "
            "cancel current subscription -> suspended -> create replacement -> active -> "
            "prove obsolete deletion cannot suspend replacement."
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
        evidence = run_phase5(
            tenant_root=Path(configured_root),
            tenant_id=args.tenant_id,
            config=config,
            timeout_seconds=args.timeout_seconds,
        )
    except (LocalH6Phase5Error, StripeBillingError, OSError, ValueError) as exc:
        raise SystemExit(f"status=failed error={exc}") from exc

    rendered = json.dumps(evidence, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
