from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from veridra.local_provider_reconcile import reconcile_local_provider
from veridra.stripe_billing import (
    StripeApiClient,
    StripeBillingConfig,
    StripeTenantBinding,
    StripeTenantBindingStore,
)
from veridra.workspace_policy import PlanName, WorkspaceConfig, WorkspaceStore

TENANT_ID = "a" * 24
NOW = datetime(2026, 10, 2, 21, 0, tzinfo=UTC)


def _config() -> StripeBillingConfig:
    return StripeBillingConfig(
        secret_key="sk_test_reconcile",
        webhook_secret="whsec_reconcile",
        price_solo="price_solo",
        price_professional="price_professional",
        price_agency="price_agency",
        trusted_origin="http://127.0.0.1:8011",
    )


def _client(config: StripeBillingConfig) -> StripeApiClient:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/subscriptions/sub_test"
        return httpx.Response(
            200,
            json={
                "id": "sub_test",
                "customer": "cus_test",
                "status": "active",
                "billing_cycle_anchor": int(
                    datetime(2026, 10, 17, tzinfo=UTC).timestamp()
                ),
                "metadata": {"veridra_tenant_id": TENANT_ID},
                "items": {
                    "data": [
                        {
                            "price": {
                                "id": "price_professional",
                            }
                        }
                    ]
                },
            },
        )

    return StripeApiClient(config, transport=httpx.MockTransport(handler))


def _state(tmp_path: Path) -> None:
    WorkspaceStore(tmp_path / TENANT_ID / "workspace").save(
        WorkspaceConfig(
            display_name="Reconcile agency",
            plan=PlanName.free,
        )
    )
    StripeTenantBindingStore(tmp_path).save(
        StripeTenantBinding(
            tenant_id=TENANT_ID,
            customer_id="cus_test",
            subscription_id="sub_test",
            updated_at=NOW,
        )
    )


def test_local_provider_reconciliation_check_is_secret_free_and_read_only(
    tmp_path: Path,
) -> None:
    _state(tmp_path)
    config = _config()

    payload = reconcile_local_provider(
        tenant_root=tmp_path,
        tenant_id=TENANT_ID,
        apply=False,
        checked_at=NOW,
        client=_client(config),
        config=config,
    )

    rendered = json.dumps(payload)
    workspace = WorkspaceStore(tmp_path / TENANT_ID / "workspace").load()

    assert payload["drift"] is True
    assert payload["applied"] is False
    assert payload["apply_requested"] is False
    assert workspace.plan is PlanName.free
    assert "sk_test_reconcile" not in rendered
    assert "whsec_reconcile" not in rendered
    assert payload["secrets_included"] is False


def test_local_provider_reconciliation_apply_projects_authoritative_state(
    tmp_path: Path,
) -> None:
    _state(tmp_path)
    config = _config()

    payload = reconcile_local_provider(
        tenant_root=tmp_path,
        tenant_id=TENANT_ID,
        apply=True,
        checked_at=NOW,
        client=_client(config),
        config=config,
    )

    workspace = WorkspaceStore(tmp_path / TENANT_ID / "workspace").load()

    assert payload["drift"] is True
    assert payload["applied"] is True
    assert payload["apply_requested"] is True
    assert workspace.plan is PlanName.professional
    assert workspace.cycle_anchor_day == 17
