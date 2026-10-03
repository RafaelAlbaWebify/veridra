from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from veridra.local_h6_acceptance import LocalH6AcceptanceError, run_phase3
from veridra.stripe_billing import (
    StripeBillingConfig,
    StripePortalSession,
    StripeSubscription,
    StripeTenantBinding,
    StripeTenantBindingStore,
)
from veridra.workspace_policy import PlanName, WorkspaceConfig, WorkspaceStore


def _config() -> StripeBillingConfig:
    return StripeBillingConfig(
        secret_key="sk_test_secret",
        webhook_secret="whsec_test",
        price_solo="price_solo",
        price_professional="price_professional",
        price_agency="price_agency",
        trusted_origin="http://127.0.0.1:8011",
    )


def _subscription(plan: PlanName) -> StripeSubscription:
    price = {
        PlanName.solo: "price_solo",
        PlanName.professional: "price_professional",
        PlanName.agency: "price_agency",
    }[plan]
    return StripeSubscription.model_validate(
        {
            "id": "sub_test",
            "customer": "cus_test",
            "status": "active",
            "billing_cycle_anchor": int(
                datetime(2026, 10, 3, tzinfo=UTC).timestamp()
            ),
            "metadata": {"veridra_tenant_id": "a" * 24},
            "items": {
                "data": [
                    {
                        "id": "si_test",
                        "price": {"id": price},
                    }
                ]
            },
        }
    )


class _FakeStripeClient:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.plan = PlanName.solo
        self.transitions: list[PlanName] = []

    def create_portal(self, *, customer_id: str) -> StripePortalSession:
        assert customer_id == "cus_test"
        return StripePortalSession(
            id="bps_test",
            url="https://billing.stripe.com/p/session/test",
        )

    def retrieve_subscription(self, subscription_id: str) -> StripeSubscription:
        assert subscription_id == "sub_test"
        return _subscription(self.plan)

    def update_subscription_plan(
        self,
        *,
        subscription_id: str,
        plan: PlanName,
    ) -> StripeSubscription:
        assert subscription_id == "sub_test"
        self.plan = plan
        self.transitions.append(plan)
        store = WorkspaceStore(self.root / ("a" * 24) / "workspace")
        current = store.load()
        store.save(
            current.model_copy(
                update={
                    "plan": plan,
                }
            )
        )
        return _subscription(plan)


class _BadPortalClient(_FakeStripeClient):
    def create_portal(self, *, customer_id: str) -> StripePortalSession:
        return StripePortalSession(
            id="bps_bad",
            url="https://example.com/not-stripe",
        )


def _bound_workspace(tmp_path: Path) -> None:
    tenant_id = "a" * 24
    WorkspaceStore(tmp_path / tenant_id / "workspace").save(
        WorkspaceConfig(
            display_name="H6 test",
            plan=PlanName.solo,
        )
    )
    StripeTenantBindingStore(tmp_path).save(
        StripeTenantBinding(
            tenant_id=tenant_id,
            customer_id="cus_test",
            subscription_id="sub_test",
            updated_at=datetime.now(UTC),
        )
    )


def test_phase3_automates_portal_upgrade_and_downgrade(tmp_path: Path) -> None:
    _bound_workspace(tmp_path)
    fake = _FakeStripeClient(tmp_path)

    evidence = run_phase3(
        tenant_root=tmp_path,
        tenant_id="a" * 24,
        config=_config(),
        timeout_seconds=1,
        client=fake,  # type: ignore[arg-type]
    )

    assert evidence["pass"] is True
    assert evidence["secrets_included"] is False
    assert fake.transitions == [PlanName.professional, PlanName.solo]
    transitions = evidence["transitions"]
    assert isinstance(transitions, list)
    assert [item["target_plan"] for item in transitions] == [
        "professional",
        "solo",
    ]
    final_state = evidence["final_state"]
    assert isinstance(final_state, dict)
    assert final_state["workspace"]["plan"] == "solo"  # type: ignore[index]


def test_phase3_rejects_unexpected_portal_destination(tmp_path: Path) -> None:
    _bound_workspace(tmp_path)

    try:
        run_phase3(
            tenant_root=tmp_path,
            tenant_id="a" * 24,
            config=_config(),
            timeout_seconds=1,
            client=_BadPortalClient(tmp_path),  # type: ignore[arg-type]
        )
    except LocalH6AcceptanceError as exc:
        assert "unexpected URL" in str(exc)
    else:
        raise AssertionError("unexpected portal destination should fail acceptance")
