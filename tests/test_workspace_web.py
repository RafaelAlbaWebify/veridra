from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from veridra.runtime import app
from veridra.workspace_policy import (
    PlanName,
    UsageEvent,
    UsageKind,
    UsageLedger,
    WorkspaceConfig,
    WorkspaceStore,
)
from veridra.workspace_web import record_usage, reserve_usage, workspace_policy_active


def test_workspace_dashboard_is_preview_until_plan_is_saved(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))  # type: ignore[attr-defined]
    client = TestClient(app)

    response = client.get("/workspace")

    assert response.status_code == 200
    assert "Preview only" in response.text
    assert "Free" in response.text
    assert not workspace_policy_active()


def test_plan_preview_and_apply_activate_policy(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))  # type: ignore[attr-defined]
    client = TestClient(app)

    preview = client.get("/workspace/plan-preview?plan=professional&cycle_anchor_day=15")
    applied = client.post(
        "/workspace/plan",
        data={"plan": "professional", "cycle_anchor_day": "15"},
        follow_redirects=False,
    )

    assert preview.status_code == 200
    assert "Monthly audits" in preview.text
    assert applied.status_code == 303
    workspace = WorkspaceStore().load()
    assert workspace.plan == PlanName.professional
    assert workspace.cycle_anchor_day == 15
    assert workspace_policy_active()


def test_usage_export_contains_current_cycle_events(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))  # type: ignore[attr-defined]
    WorkspaceStore().save(WorkspaceConfig(plan=PlanName.solo))
    UsageLedger().record(
        UsageEvent(
            kind=UsageKind.audit,
            quantity=2,
            occurred_at=datetime.now(UTC),
            related_id="assessment-1",
            note="route test",
        )
    )
    client = TestClient(app)

    response = client.get("/workspace/usage.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "assessment-1" in response.text
    assert "audit" in response.text


def test_compatibility_mode_does_not_meter_without_explicit_workspace(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))  # type: ignore[attr-defined]

    reserve_usage(UsageKind.audit)
    identifier = record_usage(UsageKind.audit, related_id="ignored")

    assert identifier == ""
    assert UsageLedger().list() == []


def test_active_workspace_records_usage(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))  # type: ignore[attr-defined]
    WorkspaceStore().save(WorkspaceConfig(plan=PlanName.solo))

    reserve_usage(UsageKind.audit)
    identifier = record_usage(UsageKind.audit, related_id="assessment-2")

    assert len(identifier) == 24
    events = UsageLedger().list()
    assert len(events) == 1
    assert events[0][1].related_id == "assessment-2"
