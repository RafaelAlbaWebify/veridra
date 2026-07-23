from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from .email_delivery import EmailAttemptStore, EmailStatus
from .lead_delivery import DeliveryStatus, LeadDeliveryStore
from .lead_store import LeadStatus, LeadStore, LeadStoreError


class CommercialOpsError(RuntimeError):
    pass


class EngagementKind(StrEnum):
    report_open = "report_open"
    cta_click = "cta_click"


class EngagementLink(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    lead_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    assessment_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    kind: EngagementKind
    destination: HttpUrl | None = None


class EngagementEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    lead_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    assessment_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    kind: EngagementKind
    occurred_at: datetime
    user_agent: str = Field(default="", max_length=300)
    referrer: str = Field(default="", max_length=500)


class RetentionPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    lead_days: int = Field(default=730, ge=30, le=3650)
    engagement_days: int = Field(default=365, ge=30, le=3650)


class RetentionPreview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    leads: tuple[str, ...]
    engagement_events: tuple[str, ...]


class CommercialSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    leads_total: int
    status_counts: dict[str, int]
    owner_counts: dict[str, int]
    follow_ups_due: int
    report_opens: int
    cta_clicks: int
    webhook_delivered: int
    webhook_failed: int
    email_delivered: int
    email_failed: int


def default_commercial_directory() -> Path:
    configured = os.environ.get("VERIDRA_DATA_DIR")
    root = Path(configured).expanduser().resolve() if configured else Path.home() / ".veridra"
    return root / "commercial"


def _canonical_bytes(model: BaseModel) -> bytes:
    return json.dumps(
        model.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def engagement_token(link: EngagementLink) -> str:
    return hashlib.sha256(_canonical_bytes(link)).hexdigest()[:32]


class EngagementStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or default_commercial_directory()
        self.links = self.directory / "links"
        self.events = self.directory / "events"

    @staticmethod
    def _valid_token(value: str) -> bool:
        return len(value) == 32 and all(char in "0123456789abcdef" for char in value)

    def create_link(self, link: EngagementLink) -> str:
        token = engagement_token(link)
        self.links.mkdir(parents=True, exist_ok=True)
        path = self.links / f"{token}.json"
        if not path.exists():
            path.write_bytes(_canonical_bytes(link))
        return token

    def load_link(self, token: str) -> EngagementLink:
        if not self._valid_token(token):
            raise CommercialOpsError("Invalid engagement token.")
        try:
            return EngagementLink.model_validate_json(
                (self.links / f"{token}.json").read_text(encoding="utf-8")
            )
        except FileNotFoundError as exc:
            raise CommercialOpsError("Engagement link was not found.") from exc
        except (OSError, ValueError) as exc:
            raise CommercialOpsError("Engagement link could not be read safely.") from exc

    def record(
        self,
        link: EngagementLink,
        *,
        occurred_at: datetime | None = None,
        user_agent: str = "",
        referrer: str = "",
    ) -> str:
        event = EngagementEvent(
            lead_id=link.lead_id,
            assessment_id=link.assessment_id,
            kind=link.kind,
            occurred_at=occurred_at or datetime.now(UTC),
            user_agent=user_agent[:300],
            referrer=referrer[:500],
        )
        content = _canonical_bytes(event)
        identifier = hashlib.sha256(content).hexdigest()[:24]
        self.events.mkdir(parents=True, exist_ok=True)
        destination = self.events / f"{identifier}.json"
        with NamedTemporaryFile(
            mode="wb",
            dir=self.events,
            prefix=f".{identifier}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        temporary_path.replace(destination)
        return identifier

    def list_events(self, *, lead_id: str | None = None) -> list[tuple[str, EngagementEvent]]:
        if not self.events.exists():
            return []
        result: list[tuple[str, EngagementEvent]] = []
        for path in sorted(self.events.glob("*.json")):
            try:
                event = EngagementEvent.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if lead_id is None or event.lead_id == lead_id:
                result.append((path.stem, event))
        return sorted(result, key=lambda item: (item[1].occurred_at, item[0]), reverse=True)

    def delete_events(self, identifiers: tuple[str, ...]) -> None:
        for identifier in identifiers:
            try:
                (self.events / f"{identifier}.json").unlink()
            except FileNotFoundError:
                continue


def retention_preview(
    policy: RetentionPolicy,
    *,
    now: datetime | None = None,
    lead_store: LeadStore | None = None,
    engagement_store: EngagementStore | None = None,
) -> RetentionPreview:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    leads = lead_store or LeadStore()
    engagements = engagement_store or EngagementStore()
    lead_cutoff = current - timedelta(days=policy.lead_days)
    event_cutoff = current - timedelta(days=policy.engagement_days)
    lead_ids = tuple(
        identifier
        for identifier, lead in leads.list_leads()
        if lead.consented_at.astimezone(UTC) < lead_cutoff
        and lead.status in {LeadStatus.lost, LeadStatus.deleted_pending}
    )
    event_ids = tuple(
        identifier
        for identifier, event in engagements.list_events()
        if event.occurred_at.astimezone(UTC) < event_cutoff
    )
    return RetentionPreview(leads=lead_ids, engagement_events=event_ids)


def apply_retention(
    preview: RetentionPreview,
    *,
    lead_store: LeadStore | None = None,
    engagement_store: EngagementStore | None = None,
) -> RetentionPreview:
    leads = lead_store or LeadStore()
    engagements = engagement_store or EngagementStore()
    for identifier in preview.leads:
        try:
            leads.delete(identifier)
        except LeadStoreError:
            continue
    engagements.delete_events(preview.engagement_events)
    return preview


def commercial_summary(
    *,
    now: datetime | None = None,
    lead_store: LeadStore | None = None,
    engagement_store: EngagementStore | None = None,
    webhook_store: LeadDeliveryStore | None = None,
    email_store: EmailAttemptStore | None = None,
) -> CommercialSummary:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    leads = lead_store or LeadStore()
    engagements = engagement_store or EngagementStore()
    webhooks = webhook_store or LeadDeliveryStore()
    emails = email_store or EmailAttemptStore()
    records = leads.list_leads()
    statuses = Counter(lead.status.value for _, lead in records)
    owners = Counter((lead.assigned_owner or "Unassigned") for _, lead in records)
    due = sum(
        lead.next_follow_up_at is not None
        and lead.next_follow_up_at.astimezone(UTC) <= current
        and lead.status not in {LeadStatus.won, LeadStatus.lost}
        for _, lead in records
    )
    events = [event for _, event in engagements.list_events()]
    webhook_attempts = [
        attempt
        for lead_id, _ in records
        for _, attempt in webhooks.list_for_lead(lead_id)
    ]
    email_attempts = [
        attempt
        for lead_id, _ in records
        for _, attempt in emails.list_for_related(lead_id)
    ]
    return CommercialSummary(
        leads_total=len(records),
        status_counts=dict(sorted(statuses.items())),
        owner_counts=dict(sorted(owners.items())),
        follow_ups_due=due,
        report_opens=sum(event.kind == EngagementKind.report_open for event in events),
        cta_clicks=sum(event.kind == EngagementKind.cta_click for event in events),
        webhook_delivered=sum(item.status == DeliveryStatus.delivered for item in webhook_attempts),
        webhook_failed=sum(item.status == DeliveryStatus.failed for item in webhook_attempts),
        email_delivered=sum(item.status == EmailStatus.delivered for item in email_attempts),
        email_failed=sum(item.status == EmailStatus.failed for item in email_attempts),
    )
