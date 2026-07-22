from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from veridra.monitoring_schedule import MonitoringSchedule


def test_manual_schedule_never_becomes_due() -> None:
    schedule = MonitoringSchedule()
    now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
    assert schedule.next_due(None, now=now) is None
    assert schedule.is_due(None, now=now) is False


def test_daily_schedule_uses_local_time_and_utc_output() -> None:
    schedule = MonitoringSchedule(cadence="daily", timezone="Europe/Madrid", hour=9)
    last_run = datetime(2026, 7, 21, 8, 0, tzinfo=UTC)
    due = schedule.next_due(last_run)
    assert due == datetime(2026, 7, 22, 7, 0, tzinfo=UTC)


def test_weekly_schedule_rolls_to_requested_weekday() -> None:
    schedule = MonitoringSchedule(
        cadence="weekly",
        timezone="UTC",
        weekday=0,
        hour=10,
    )
    last_run = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    assert schedule.next_due(last_run) == datetime(2026, 7, 27, 10, 0, tzinfo=UTC)


def test_monthly_schedule_rolls_to_next_month() -> None:
    schedule = MonitoringSchedule(
        cadence="monthly",
        timezone="UTC",
        day_of_month=15,
        hour=8,
    )
    last_run = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    assert schedule.next_due(last_run) == datetime(2026, 8, 15, 8, 0, tzinfo=UTC)


def test_first_non_manual_run_is_due_immediately() -> None:
    schedule = MonitoringSchedule(cadence="daily", timezone="UTC")
    now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
    assert schedule.next_due(None, now=now) == now
    assert schedule.is_due(None, now=now) is True


@pytest.mark.parametrize(
    "values",
    [
        {"cadence": "weekly", "timezone": "UTC"},
        {"cadence": "daily", "timezone": "UTC", "weekday": 1},
        {"cadence": "monthly", "timezone": "UTC"},
        {"cadence": "daily", "timezone": "UTC", "day_of_month": 3},
        {"cadence": "daily", "timezone": "Not/AZone"},
    ],
)
def test_invalid_schedule_combinations_are_rejected(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MonitoringSchedule.model_validate(values)
