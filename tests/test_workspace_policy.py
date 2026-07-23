from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from veridra.workspace_policy import (
    PLAN_CATALOGUE,
    PlanName,
    UsageEvent,
    UsageKind,
    UsageLedger,
    WorkspaceConfig,
    WorkspacePolicyError,
    WorkspaceStatus,
    WorkspaceStore,
    quota_decision,
    require_quota,
    usage_period,
)


def test_plan_catalogue_matches_product_tiers() -> None:
    assert PLAN_CATALOGUE[PlanName.free].max_projects == 1
    assert PLAN_CATALOGUE[PlanName.solo].monthly_audits == 50
    assert PLAN_CATALOGUE[PlanName.professional].white_label is True
    assert PLAN_CATALOGUE[PlanName.professional].embedded_lead_forms is False
    assert PLAN_CATALOGUE[PlanName.agency].embedded_lead_forms is True
    assert PLAN_CATALOGUE[PlanName.agency].max_users == 10


def test_workspace_store_defaults_and_persists_atomically(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path)
    assert store.load().plan == PlanName.free

    workspace = WorkspaceConfig(
        display_name="Example Agency",
        plan=PlanName.professional,
        cycle_anchor_day=15,
    )
    store.save(workspace)

    assert store.load() == workspace
    assert list(tmp_path.glob("*.tmp")) == []


def test_usage_period_honours_anchor_before_and_after_day() -> None:
    workspace = WorkspaceConfig(cycle_anchor_day=15)

    before = usage_period(workspace, now=datetime(2026, 7, 10, 12, tzinfo=UTC))
    assert before.starts_at == datetime(2026, 6, 15, tzinfo=UTC)
    assert before.ends_at == datetime(2026, 7, 15, tzinfo=UTC)

    after = usage_period(workspace, now=datetime(2026, 7, 20, 12, tzinfo=UTC))
    assert after.starts_at == datetime(2026, 7, 15, tzinfo=UTC)
    assert after.ends_at == datetime(2026, 8, 15, tzinfo=UTC)


def test_usage_ledger_is_append_only_and_period_bounded(tmp_path: Path) -> None:
    ledger = UsageLedger(tmp_path)
    workspace = WorkspaceConfig(cycle_anchor_day=1)
    period = usage_period(workspace, now=datetime(2026, 7, 20, tzinfo=UTC))

    first = UsageEvent(
        kind=UsageKind.audit,
        quantity=1,
        occurred_at=datetime(2026, 7, 2, tzinfo=UTC),
        related_id="a" * 24,
    )
    old = UsageEvent(
        kind=UsageKind.audit,
        quantity=3,
        occurred_at=datetime(2026, 6, 30, tzinfo=UTC),
    )
    first_id = ledger.record(first)
    assert ledger.record(first) == first_id
    ledger.record(old)

    assert ledger.totals(period) == {UsageKind.audit: 1}
    assert len(ledger.list()) == 2


def test_quota_decision_and_exhaustion(tmp_path: Path) -> None:
    ledger = UsageLedger(tmp_path)
    workspace = WorkspaceConfig(plan=PlanName.free)
    now = datetime(2026, 7, 20, tzinfo=UTC)

    for day in (2, 3, 4):
        ledger.record(
            UsageEvent(
                kind=UsageKind.audit,
                occurred_at=datetime(2026, 7, day, tzinfo=UTC),
                related_id=str(day),
            )
        )

    decision = quota_decision(workspace, ledger, UsageKind.audit, now=now)
    assert decision.allowed is False
    assert decision.used == 3
    assert decision.limit == 3
    assert decision.remaining == 0

    try:
        require_quota(workspace, ledger, UsageKind.audit, now=now)
    except WorkspacePolicyError as exc:
        assert "exhausted" in str(exc)
    else:
        raise AssertionError("Expected quota enforcement to reject the fourth free audit.")


def test_unlimited_operational_meter_and_suspended_workspace(tmp_path: Path) -> None:
    ledger = UsageLedger(tmp_path)
    active = WorkspaceConfig(plan=PlanName.agency)
    metered = quota_decision(active, ledger, UsageKind.email_attempt)
    assert metered.allowed is True
    assert metered.limit is None
    assert metered.remaining is None

    suspended = WorkspaceConfig(status=WorkspaceStatus.suspended)
    blocked = quota_decision(suspended, ledger, UsageKind.audit)
    assert blocked.allowed is False
    assert blocked.reason == "The local workspace is suspended."
