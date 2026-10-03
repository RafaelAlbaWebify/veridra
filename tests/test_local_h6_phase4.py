from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from veridra.local_h6_phase4 import LocalH6Phase4Error, run_phase4
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
    status: str,
    default_payment_method: str | None,
    latest_invoice: str | None,
) -> StripeSubscription:
    return StripeSubscription.model_validate(
        {
            "id": "sub_test",
            "customer": "cus_test",
            "status": status,
            "billing_cycle_anchor": int(
                datetime(2026, 10, 3, tzinfo=UTC).timestamp()
            ),
            "latest_invoice": latest_invoice,
            "default_payment_method": default_payment_method,
            "metadata": {"veridra_tenant_id": TENANT_ID},
            "items": {
                "data": [
                    {
                        "id": "si_test",
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
        self.status = "active"
        self.default_payment_method: str | None = "pm_original"
        self.latest_invoice: str | None = "in_original"
        self.paid_invoice: str | None = None
        self.restored_original = False

    def retrieve_subscription(self, subscription_id: str) -> StripeSubscription:
        assert subscription_id == "sub_test"
        return _subscription(
            status=self.status,
            default_payment_method=self.default_payment_method,
            latest_invoice=self.latest_invoice,
        )

    def attach_payment_method(
        self,
        *,
        payment_method_id: str,
        customer_id: str,
    ) -> str:
        assert customer_id == "cus_test"
        return payment_method_id

    def update_subscription_payment_method(
        self,
        *,
        subscription_id: str,
        payment_method_id: str,
        reset_billing_cycle: bool = False,
        payment_behavior: str = "allow_incomplete",
    ) -> StripeSubscription:
        assert subscription_id == "sub_test"
        assert payment_behavior == "allow_incomplete"
        self.default_payment_method = payment_method_id
        workspace = WorkspaceStore(self.root / TENANT_ID / "workspace")
        current = workspace.load()
        if payment_method_id == "pm_card_chargeCustomerFail":
            assert reset_billing_cycle is True
            self.status = "past_due"
            self.latest_invoice = "in_failed"
            workspace.save(
                current.model_copy(update={"status": WorkspaceStatus.suspended})
            )
        elif payment_method_id == "pm_original":
            self.restored_original = True
        return self.retrieve_subscription(subscription_id)

    def pay_invoice(self, invoice_id: str) -> dict[str, object]:
        assert invoice_id == "in_failed"
        self.paid_invoice = invoice_id
        self.status = "active"
        workspace = WorkspaceStore(self.root / TENANT_ID / "workspace")
        current = workspace.load()
        workspace.save(current.model_copy(update={"status": WorkspaceStatus.active}))
        return {"id": invoice_id, "status": "paid"}


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
            subscription_id="sub_test",
            updated_at=datetime.now(UTC),
        )
    )


def test_phase4_automates_failure_suspension_and_recovery(tmp_path: Path) -> None:
    _bound_workspace(tmp_path)
    fake = _FakeStripeClient(tmp_path)

    evidence = run_phase4(
        tenant_root=tmp_path,
        tenant_id=TENANT_ID,
        config=_config(),
        timeout_seconds=1,
        client=fake,
    )

    assert evidence["pass"] is True
    assert evidence["secrets_included"] is False
    assert fake.paid_invoice == "in_failed"
    assert fake.restored_original is True
    failure = evidence["failure"]
    assert isinstance(failure, dict)
    assert failure["provider_status"] == "past_due"
    assert failure["workspace_status"] == "suspended"
    recovery = evidence["recovery"]
    assert isinstance(recovery, dict)
    assert recovery["provider_status"] == "active"
    assert recovery["workspace_status"] == "active"
    final_state = evidence["final_state"]
    assert isinstance(final_state, dict)
    assert final_state == {
        "provider_status": "active",
        "workspace_plan": "solo",
        "workspace_status": "active",
    }


def test_phase4_requires_solo_active_start(tmp_path: Path) -> None:
    _bound_workspace(tmp_path)
    workspace = WorkspaceStore(tmp_path / TENANT_ID / "workspace")
    workspace.save(
        workspace.load().model_copy(update={"plan": PlanName.professional})
    )

    try:
        run_phase4(
            tenant_root=tmp_path,
            tenant_id=TENANT_ID,
            config=_config(),
            timeout_seconds=1,
            client=_FakeStripeClient(tmp_path),
        )
    except LocalH6Phase4Error as exc:
        assert "Solo/active" in str(exc)
    else:
        raise AssertionError("non-Solo workspace should fail Phase 4 acceptance")
