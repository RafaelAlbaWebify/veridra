from __future__ import annotations

from calendar import monthrange
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MonitoringCadence(StrEnum):
    manual = "manual"
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"


class MonitoringSchedule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    cadence: MonitoringCadence = MonitoringCadence.manual
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    hour: int = Field(default=9, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    weekday: int | None = Field(default=None, ge=0, le=6)
    day_of_month: int | None = Field(default=None, ge=1, le=28)

    @model_validator(mode="after")
    def validate_schedule(self) -> MonitoringSchedule:
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Unknown monitoring timezone.") from exc
        if self.cadence == MonitoringCadence.weekly and self.weekday is None:
            raise ValueError("Weekly monitoring requires a weekday.")
        if self.cadence != MonitoringCadence.weekly and self.weekday is not None:
            raise ValueError("Weekday is only valid for weekly monitoring.")
        if self.cadence == MonitoringCadence.monthly and self.day_of_month is None:
            raise ValueError("Monthly monitoring requires a day of month.")
        if self.cadence != MonitoringCadence.monthly and self.day_of_month is not None:
            raise ValueError("Day of month is only valid for monthly monitoring.")
        return self

    def next_due(self, last_run: datetime | None, *, now: datetime | None = None) -> datetime | None:
        if self.cadence == MonitoringCadence.manual:
            return None
        zone = ZoneInfo(self.timezone)
        current = (now or datetime.now(UTC)).astimezone(zone)
        if last_run is None:
            return current.astimezone(UTC)
        local_last = last_run.astimezone(zone)
        if self.cadence == MonitoringCadence.daily:
            candidate = local_last.replace(
                hour=self.hour,
                minute=self.minute,
                second=0,
                microsecond=0,
            )
            if candidate <= local_last:
                candidate += timedelta(days=1)
        elif self.cadence == MonitoringCadence.weekly:
            assert self.weekday is not None
            days = (self.weekday - local_last.weekday()) % 7
            candidate = local_last.replace(
                hour=self.hour,
                minute=self.minute,
                second=0,
                microsecond=0,
            ) + timedelta(days=days)
            if candidate <= local_last:
                candidate += timedelta(days=7)
        else:
            assert self.day_of_month is not None
            year = local_last.year
            month = local_last.month
            day = min(self.day_of_month, monthrange(year, month)[1])
            candidate = local_last.replace(
                day=day,
                hour=self.hour,
                minute=self.minute,
                second=0,
                microsecond=0,
            )
            if candidate <= local_last:
                if month == 12:
                    year += 1
                    month = 1
                else:
                    month += 1
                day = min(self.day_of_month, monthrange(year, month)[1])
                candidate = candidate.replace(year=year, month=month, day=day)
        return candidate.astimezone(UTC)

    def is_due(self, last_run: datetime | None, *, now: datetime | None = None) -> bool:
        due = self.next_due(last_run, now=now)
        if due is None:
            return False
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        return due <= current.astimezone(UTC)
