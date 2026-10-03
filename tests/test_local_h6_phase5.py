from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from veridra.local_h6_phase5 import LocalH6Phase5Error, run_phase5
from veridra.stripe_billing import (
    StripeApiClient,
    StripeBillingConfig,
    StripeSubscription,
    StripeTenantBinding,
    StripeTenantBindingStore,
)
from veridra.workspace_policy import (
    PlanName,
    WorkspaceConfig,
    WorkspaceStatus,
    WorkspaceStore,
)

TENANT_ID = "a" * 24


def _config() -> StripeBillingConfig:
    return StripeBillingConfig(
        secret_key="sk_test_secret",
        webhook_secret="whsec_test",
        price_solo="price_solo",
        price_professional="price_professional",
        price_agency="price_agency",
        trusted_origin="http://127.0.0.1:8011",
    )


def _subscription(
    *,
    subscription_id: str,
    status: str,
    customer_id: str = "cus_test",
) -> StripeSubscription:
    return StripeSubscription.model_validate(
        {
            "id": subscription_id,
            "customer": customer_id,
            "status": status,
            "billing_cycle_anchor": int(
                datetime(2026, 10, 3, tzinfo=UTC).timestamp()
            ),
            "default_payment_method": "pm_original",
            "metadata": {"veridra_tenant_id": TENANT_ID},
            "items": {
                "data": [
                    {
                        "id": f"si_{subscription_id}",
                        "price": {"id": "price_solo"},
                    }
                ]
            },
        }
    )


class _FakeStripeClient(StripeApiClient):
    def __init__(self, root: Path) -> None:
        super().__init__(_config())
        self.root = root
        self.current: dict[str, StripeSubscription] = {
            "sub_old": _subscription(subscription_id="sub_old", status="active")
        }

    def retrieve_subscription(self, subscription_id: str) -> StripeSubscription:
        return self.current[subscription_id]

    def cancel_subscription(self, subscription_id: str) -> StripeSubscription:
        canceled = _subscription(subscription_id=subscription_id, status="canceled")
        self.current[subscription_id] = canceled
        workspace = WorkspaceStore(self.root / TENANT_ID / "workspace")
        current_workspace = workspace.load()
        workspace.save(
            current_workspace.model_copy(update={"status": WorkspaceStatus.suspended})
        )
        return canceled

    def create_subscription(
        self,
        *,
        tenant_id: str,
        customer_id: str,
        plan: PlanName,
        default_payment_method: str | None = None,
    ) -> StripeSubscription:
        assert tenant_id == TENANT_ID
        assert customer_id == "cus_test"
        assert plan is PlanName.solo
        assert default_payment_method == "pm_original"
        replacement = _subscription(
            subscription_id="sub_new",
            status="active",
            customer_id=customer_id,
        )
        self.current[replacement.id] = replacement
        StripeTenantBindingStore(self.root).save(
            StripeTenantBinding(
                tenant_id=TENANT_ID,
                customer_id=customer_id,
                subscription_id=replacement.id,
                updated_at=datetime.now(UTC),
            )
        )
        workspace = WorkspaceStore(self.root / TENANT_ID / "workspace")
        current_workspace = workspace.load()
        workspace.save(
            current_workspace.model_copy(update={"status": WorkspaceStatus.active})
        )
        return replacement


def _bound_workspace(tmp_path: Path) -> None:
    WorkspaceStore(tmp_path / TENANT_ID / "workspace").save(
        WorkspaceConfig(
            display_name="H6 test",
            plan=PlanName.solo,
            status=WorkspaceStatus.active,
            cycle_anchor_day=3,
        )
    )
    StripeTenantBindingStore(tmp_path).save(
        StripeTenantBinding(
            tenant_id=TENANT_ID,
            customer_id="cus_test",
            subscription_id="sub_old",
            updated_at=datetime.now(UTC),
        )
    )


def test_phase5_cancels_replaces_and_guards_obsolete_deletion(tmp_path: Path) -> None:
    _bound_workspace(tmp_path)
    fake = _FakeStripeClient(tmp_path)

    evidence = run_phase5(
        tenant_root=tmp_path,
        tenant_id=TENANT_ID,
        config=_config(),
        timeout_seconds=1,
        client=fake,
    )

    assert evidence["pass"] is True
    assert evidence["secrets_included"] is False
    cancellation = evidence["cancellation"]
    assert isinstance(cancellation, dict)
    assert cancellation["provider_status"] == "canceled"
    assert cancellation["workspace_status"] == "suspended"
    replacement = evidence["replacement"]
    assert isinstance(replacement, dict)
    assert replacement["provider_status"] == "active"
    assert replacement["workspace_status"] == "active"
    guard = evidence["obsolete_deletion_guard"]
    assert isinstance(guard, dict)
    assert guard["applied"] is False
    assert guard["current_binding_preserved"] is True
    assert "not the current tenant binding" in str(guard["reason"])
    final_state = evidence["final_state"]
    assert isinstance(final_state, dict)
    assert final_state == {
        "provider_status": "active",
        "workspace_plan": "solo",
        "workspace_status": "active",
        "binding_subscription_id": "sub_new",
    }


def test_phase5_requires_solo_active_start(tmp_path: Path) -> None:
    _bound_workspace(tmp_path)
    workspace = WorkspaceStore(tmp_path / TENANT_ID / "workspace")
    workspace.save(
        workspace.load().model_copy(update={"status": WorkspaceStatus.suspended})
    )

    try:
        run_phase5(
            tenant_root=tmp_path,
            tenant_id=TENANT_ID,
            config=_config(),
            timeout_seconds=1,
            client=_FakeStripeClient(tmp_path),
        )
    except LocalH6Phase5Error as exc:
        assert "Solo/active" in str(exc)
    else:
        raise AssertionError("suspended workspace should fail Phase 5 acceptance")
