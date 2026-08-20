from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import veridra.subscription_authority as subscription_module
from veridra.subscription_authority import (
    SubscriptionAuthority,
    SubscriptionAuthorityError,
    SubscriptionUpdate,
)
from veridra.workspace_policy import PlanName, WorkspaceConfig, WorkspaceStatus, WorkspaceStore

TENANT_ID = "a" * 24
NOW = datetime(2026, 8, 20, 14, 0, tzinfo=UTC)


def _update(
    *,
    event_id: str = "evt-1",
    occurred_at: datetime = NOW,
    plan: PlanName = PlanName.agency,
    status: WorkspaceStatus = WorkspaceStatus.active,
) -> SubscriptionUpdate:
    return SubscriptionUpdate(
        tenant_id=TENANT_ID,
        provider="test-provider",
        provider_event_id=event_id,
        external_subscription_id="sub-123",
        plan=plan,
        status=status,
        cycle_anchor_day=20,
        occurred_at=occurred_at,
    )


def _workspace(
    tmp_path: Path,
    config: WorkspaceConfig | None = None,
) -> WorkspaceStore:
    workspace = WorkspaceStore(tmp_path / TENANT_ID / "workspace")
    workspace.save(config or WorkspaceConfig(display_name="Customer workspace"))
    return workspace


def test_subscription_event_projects_entitlements_and_preserves_workspace_name(
    tmp_path: Path,
) -> None:
    workspace = _workspace(
        tmp_path,
        WorkspaceConfig(display_name="Customer workspace", plan=PlanName.free),
    )
    authority = SubscriptionAuthority(tmp_path)

    result = authority.apply(_update(), applied_at=NOW + timedelta(seconds=1))

    assert result.applied is True
    assert result.workspace.display_name == "Customer workspace"
    assert result.workspace.plan is PlanName.agency
    assert result.workspace.status is WorkspaceStatus.active
    assert result.workspace.cycle_anchor_day == 20
    assert workspace.load() == result.workspace
    events = authority.list_events(TENANT_ID)
    assert len(events) == 1
    assert events[0].previous_workspace.plan is PlanName.free
    assert events[0].projected_workspace.plan is PlanName.agency


def test_subscription_authority_refuses_to_create_unknown_tenant_workspace(
    tmp_path: Path,
) -> None:
    authority = SubscriptionAuthority(tmp_path)

    with pytest.raises(SubscriptionAuthorityError, match="unknown tenant workspace"):
        authority.apply(_update(), applied_at=NOW + timedelta(seconds=1))

    assert not (tmp_path / TENANT_ID / "workspace" / "workspace.json").exists()


def test_replaying_same_provider_event_is_idempotent(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    authority = SubscriptionAuthority(tmp_path)
    update = _update()

    first = authority.apply(update, applied_at=NOW + timedelta(seconds=1))
    authority.apply(
        _update(
            event_id="evt-2",
            occurred_at=NOW + timedelta(minutes=1),
            plan=PlanName.professional,
        ),
        applied_at=NOW + timedelta(minutes=1, seconds=1),
    )
    replay = authority.apply(update, applied_at=NOW + timedelta(minutes=2))

    assert first.applied is True
    assert replay.applied is False
    assert replay.event_key == first.event_key
    assert replay.workspace == workspace.load()
    assert replay.workspace.plan is PlanName.professional
    assert len(authority.list_events(TENANT_ID)) == 2


def test_provider_event_identity_cannot_be_reused_with_different_data(tmp_path: Path) -> None:
    _workspace(tmp_path)
    authority = SubscriptionAuthority(tmp_path)
    authority.apply(_update(), applied_at=NOW + timedelta(seconds=1))

    with pytest.raises(SubscriptionAuthorityError, match="identity was reused"):
        authority.apply(
            _update(plan=PlanName.professional),
            applied_at=NOW + timedelta(minutes=1),
        )


def test_stale_and_equal_timestamp_events_cannot_replace_current_state(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    authority = SubscriptionAuthority(tmp_path)
    authority.apply(_update(event_id="evt-new"), applied_at=NOW + timedelta(seconds=1))

    with pytest.raises(SubscriptionAuthorityError, match="Stale subscription event"):
        authority.apply(
            _update(event_id="evt-old", occurred_at=NOW - timedelta(seconds=1)),
            applied_at=NOW + timedelta(minutes=1),
        )

    with pytest.raises(SubscriptionAuthorityError, match="Ambiguous subscription events"):
        authority.apply(
            _update(event_id="evt-same-time"),
            applied_at=NOW + timedelta(minutes=1),
        )

    assert workspace.load().plan is PlanName.agency


def test_suspension_event_projects_workspace_status(tmp_path: Path) -> None:
    _workspace(tmp_path)
    authority = SubscriptionAuthority(tmp_path)
    authority.apply(_update(), applied_at=NOW + timedelta(seconds=1))

    result = authority.apply(
        _update(
            event_id="evt-suspended",
            occurred_at=NOW + timedelta(minutes=1),
            status=WorkspaceStatus.suspended,
        ),
        applied_at=NOW + timedelta(minutes=1, seconds=1),
    )

    assert result.workspace.status is WorkspaceStatus.suspended
    assert result.workspace.plan is PlanName.agency


def test_event_evidence_failure_rolls_back_workspace_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = WorkspaceConfig(display_name="Keep me", plan=PlanName.solo)
    workspace = _workspace(tmp_path, original)
    authority = SubscriptionAuthority(tmp_path)

    def fail_event_write(path: Path, payload: object) -> None:
        raise OSError("simulated event write failure")

    monkeypatch.setattr(subscription_module, "_atomic_json", fail_event_write)

    with pytest.raises(SubscriptionAuthorityError, match="could not be projected safely"):
        authority.apply(_update(), applied_at=NOW + timedelta(seconds=1))

    assert workspace.load() == original
    assert authority.list_events(TENANT_ID) == []
