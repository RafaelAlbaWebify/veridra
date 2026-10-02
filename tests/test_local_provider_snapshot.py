from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from veridra.local_provider_snapshot import (
    LocalProviderSnapshotError,
    build_local_provider_snapshot,
)
from veridra.stripe_billing import (
    StripeCheckoutReservation,
    StripeCheckoutReservationStore,
    StripeTenantBinding,
    StripeTenantBindingStore,
)
from veridra.workspace_policy import PlanName, WorkspaceConfig, WorkspaceStatus, WorkspaceStore

TENANT_ID = "0123456789abcdef01234567"
NOW = datetime(2026, 10, 2, 20, 0, tzinfo=UTC)


def test_local_provider_snapshot_is_read_only_and_secret_free(tmp_path: Path) -> None:
    workspace_dir = tmp_path / TENANT_ID / "workspace"
    WorkspaceStore(workspace_dir).save(
        WorkspaceConfig(
            display_name="Acceptance agency",
            plan=PlanName.professional,
            status=WorkspaceStatus.active,
            cycle_anchor_day=12,
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
    reservation_store = StripeCheckoutReservationStore(tmp_path)
    reservation_path = reservation_store._path(TENANT_ID)
    reservation_path.parent.mkdir(parents=True, exist_ok=True)
    reservation_path.write_text(
        StripeCheckoutReservation(
            tenant_id=TENANT_ID,
            plan=PlanName.agency,
            idempotency_key="veridra-checkout-acceptance-1234567890",
            created_at=NOW,
            expires_at=NOW + timedelta(minutes=30),
        ).model_dump_json(),
        encoding="utf-8",
    )

    payload = build_local_provider_snapshot(
        tenant_root=tmp_path,
        tenant_id=TENANT_ID,
        captured_at=NOW,
    )
    rendered = json.dumps(payload)

    assert payload["workspace"] == {
        "plan": "professional",
        "status": "active",
        "cycle_anchor_day": 12,
    }
    assert payload["stripe"]["bound"] is True
    assert payload["stripe"]["customer_id"] == "cus_test"
    assert payload["stripe"]["subscription_id"] == "sub_test"
    assert payload["stripe"]["checkout_reservation"]["plan"] == "agency"
    assert payload["secrets_included"] is False
    assert "idempotency" not in rendered.lower()
    assert "secret" not in rendered.lower().replace('"secrets_included": false', "")


def test_local_provider_snapshot_handles_unbound_workspace(tmp_path: Path) -> None:
    WorkspaceStore(tmp_path / TENANT_ID / "workspace").save(WorkspaceConfig())

    payload = build_local_provider_snapshot(
        tenant_root=tmp_path,
        tenant_id=TENANT_ID,
        captured_at=NOW,
    )

    assert payload["stripe"]["bound"] is False
    assert payload["stripe"]["customer_id"] is None
    assert payload["stripe"]["subscription_id"] is None
    assert payload["stripe"]["checkout_reservation"] is None


@pytest.mark.parametrize(
    "tenant_id",
    ["", "abc", "g123456789abcdef01234567", "../escape-tenant"],
)
def test_local_provider_snapshot_rejects_invalid_tenant_ids(
    tmp_path: Path,
    tenant_id: str,
) -> None:
    with pytest.raises(LocalProviderSnapshotError):
        build_local_provider_snapshot(
            tenant_root=tmp_path,
            tenant_id=tenant_id,
            captured_at=NOW,
        )
