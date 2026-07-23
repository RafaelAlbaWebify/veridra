from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel, ConfigDict, Field


class WorkspacePolicyError(RuntimeError):
    pass


class PlanName(StrEnum):
    free = "free"
    solo = "solo"
    professional = "professional"
    agency = "agency"


class WorkspaceStatus(StrEnum):
    active = "active"
    suspended = "suspended"


class UsageKind(StrEnum):
    audit = "audit"
    crawled_page = "crawled_page"
    pdf = "pdf"
    export = "export"
    lead_submission = "lead_submission"
    monitoring_run = "monitoring_run"
    webhook_attempt = "webhook_attempt"
    email_attempt = "email_attempt"


class PlanEntitlements(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: PlanName
    max_projects: int = Field(ge=1)
    monthly_audits: int = Field(ge=1)
    monthly_crawled_pages: int = Field(ge=1)
    monthly_pdfs: int = Field(ge=0)
    monthly_exports: int = Field(ge=0)
    monthly_lead_submissions: int = Field(ge=0)
    monthly_monitoring_runs: int = Field(ge=0)
    white_label: bool
    embedded_lead_forms: bool
    max_users: int = Field(ge=1)

    def limit_for(self, kind: UsageKind) -> int | None:
        return {
            UsageKind.audit: self.monthly_audits,
            UsageKind.crawled_page: self.monthly_crawled_pages,
            UsageKind.pdf: self.monthly_pdfs,
            UsageKind.export: self.monthly_exports,
            UsageKind.lead_submission: self.monthly_lead_submissions,
            UsageKind.monitoring_run: self.monthly_monitoring_runs,
            UsageKind.webhook_attempt: None,
            UsageKind.email_attempt: None,
        }[kind]


PLAN_CATALOGUE: dict[PlanName, PlanEntitlements] = {
    PlanName.free: PlanEntitlements(
        name=PlanName.free,
        max_projects=1,
        monthly_audits=3,
        monthly_crawled_pages=30,
        monthly_pdfs=0,
        monthly_exports=0,
        monthly_lead_submissions=0,
        monthly_monitoring_runs=0,
        white_label=False,
        embedded_lead_forms=False,
        max_users=1,
    ),
    PlanName.solo: PlanEntitlements(
        name=PlanName.solo,
        max_projects=10,
        monthly_audits=50,
        monthly_crawled_pages=5_000,
        monthly_pdfs=50,
        monthly_exports=50,
        monthly_lead_submissions=0,
        monthly_monitoring_runs=25,
        white_label=False,
        embedded_lead_forms=False,
        max_users=1,
    ),
    PlanName.professional: PlanEntitlements(
        name=PlanName.professional,
        max_projects=25,
        monthly_audits=150,
        monthly_crawled_pages=75_000,
        monthly_pdfs=150,
        monthly_exports=150,
        monthly_lead_submissions=250,
        monthly_monitoring_runs=100,
        white_label=True,
        embedded_lead_forms=False,
        max_users=3,
    ),
    PlanName.agency: PlanEntitlements(
        name=PlanName.agency,
        max_projects=100,
        monthly_audits=500,
        monthly_crawled_pages=1_000_000,
        monthly_pdfs=500,
        monthly_exports=500,
        monthly_lead_submissions=2_000,
        monthly_monitoring_runs=500,
        white_label=True,
        embedded_lead_forms=True,
        max_users=10,
    ),
}


class WorkspaceConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    display_name: str = Field(default="Local Veridra workspace", min_length=1, max_length=120)
    plan: PlanName = PlanName.free
    status: WorkspaceStatus = WorkspaceStatus.active
    cycle_anchor_day: int = Field(default=1, ge=1, le=28)


class UsageEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: UsageKind
    quantity: int = Field(default=1, ge=1, le=2_000_000)
    occurred_at: datetime
    related_id: str = Field(default="", max_length=120)
    note: str = Field(default="", max_length=240)


class UsagePeriod(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    starts_at: datetime
    ends_at: datetime


class QuotaDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed: bool
    kind: UsageKind
    limit: int | None
    used: int
    requested: int
    remaining: int | None
    reason: str


def default_workspace_directory() -> Path:
    configured = os.environ.get("VERIDRA_DATA_DIR")
    root = Path(configured).expanduser().resolve() if configured else Path.home() / ".veridra"
    return root / "workspace"


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(content)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


class WorkspaceStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or default_workspace_directory()
        self.path = self.directory / "workspace.json"

    def load(self) -> WorkspaceConfig:
        if not self.path.exists():
            return WorkspaceConfig()
        try:
            return WorkspaceConfig.model_validate_json(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise WorkspacePolicyError("Workspace configuration could not be read safely.") from exc

    def save(self, workspace: WorkspaceConfig) -> None:
        content = json.dumps(
            workspace.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        _atomic_write(self.path, content)


class UsageLedger:
    def __init__(self, directory: Path | None = None) -> None:
        root = directory or default_workspace_directory()
        self.directory = root / "usage"

    def record(self, event: UsageEvent) -> str:
        content = json.dumps(
            event.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        identifier = hashlib.sha256(content).hexdigest()[:24]
        destination = self.directory / f"{identifier}.json"
        if not destination.exists():
            _atomic_write(destination, content)
        return identifier

    def list(self, *, period: UsagePeriod | None = None) -> list[tuple[str, UsageEvent]]:
        if not self.directory.exists():
            return []
        events: list[tuple[str, UsageEvent]] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                event = UsageEvent.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            occurred = event.occurred_at.astimezone(UTC)
            if period is None or period.starts_at <= occurred < period.ends_at:
                events.append((path.stem, event))
        return sorted(events, key=lambda item: (item[1].occurred_at, item[0]))

    def totals(self, period: UsagePeriod) -> dict[UsageKind, int]:
        counter = Counter[UsageKind]()
        for _, event in self.list(period=period):
            counter[event.kind] += event.quantity
        return dict(counter)


def usage_period(workspace: WorkspaceConfig, *, now: datetime | None = None) -> UsagePeriod:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    anchor = workspace.cycle_anchor_day
    if current.day >= anchor:
        start = current.replace(day=anchor, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
    else:
        end = current.replace(day=anchor, hour=0, minute=0, second=0, microsecond=0)
        if end.month == 1:
            start = end.replace(year=end.year - 1, month=12)
        else:
            start = end.replace(month=end.month - 1)
    return UsagePeriod(starts_at=start, ends_at=end)


def quota_decision(
    workspace: WorkspaceConfig,
    ledger: UsageLedger,
    kind: UsageKind,
    *,
    requested: int = 1,
    now: datetime | None = None,
) -> QuotaDecision:
    if requested < 1:
        raise ValueError("Requested usage must be at least one.")
    if workspace.status != WorkspaceStatus.active:
        return QuotaDecision(
            allowed=False,
            kind=kind,
            limit=0,
            used=0,
            requested=requested,
            remaining=0,
            reason="The local workspace is suspended.",
        )
    entitlement = PLAN_CATALOGUE[workspace.plan]
    limit = entitlement.limit_for(kind)
    period = usage_period(workspace, now=now)
    used = ledger.totals(period).get(kind, 0)
    if limit is None:
        return QuotaDecision(
            allowed=True,
            kind=kind,
            limit=None,
            used=used,
            requested=requested,
            remaining=None,
            reason="This operational event is metered but not quota-limited.",
        )
    remaining = max(limit - used, 0)
    allowed = requested <= remaining
    return QuotaDecision(
        allowed=allowed,
        kind=kind,
        limit=limit,
        used=used,
        requested=requested,
        remaining=remaining,
        reason=(
            "Usage is within the active local plan allowance."
            if allowed
            else f"The {workspace.plan.value} plan allowance for {kind.value} is exhausted."
        ),
    )


def require_quota(
    workspace: WorkspaceConfig,
    ledger: UsageLedger,
    kind: UsageKind,
    *,
    requested: int = 1,
    now: datetime | None = None,
) -> QuotaDecision:
    decision = quota_decision(workspace, ledger, kind, requested=requested, now=now)
    if not decision.allowed:
        raise WorkspacePolicyError(decision.reason)
    return decision
