from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class ProspectStatus(StrEnum):
    new = "new"
    needs_review = "needs_review"
    qualified = "qualified"
    shortlisted = "shortlisted"
    ready_for_audit = "ready_for_audit"
    audited = "audited"
    approved_for_outreach = "approved_for_outreach"
    contacted = "contacted"
    responded = "responded"
    conversation = "conversation"
    proposal = "proposal"
    customer = "customer"
    lost = "lost"
    unsuitable = "unsuitable"
    duplicate = "duplicate"
    archived = "archived"


class ProspectDecision(StrEnum):
    send_to_audit = "send_to_audit"
    hold = "hold"
    reject = "reject"


class ProspectRejectionReason(StrEnum):
    business_inactive = "BUSINESS_INACTIVE"
    too_small_low_value = "TOO_SMALL_LOW_VALUE"
    too_large = "TOO_LARGE"
    website_not_important = "WEBSITE_NOT_IMPORTANT"
    internal_web_team = "INTERNAL_WEB_TEAM"
    agency_present = "AGENCY_PRESENT"
    no_contact_route = "NO_CONTACT_ROUTE"
    tech_too_complex = "TECH_TOO_COMPLEX"
    no_meaningful_findings = "NO_MEANINGFUL_FINDINGS"
    findings_not_fixable = "FINDINGS_NOT_FIXABLE"
    fix_too_large_for_offer = "FIX_TOO_LARGE_FOR_OFFER"
    low_commercial_impact = "LOW_COMMERCIAL_IMPACT"
    evidence_uncertain = "EVIDENCE_UNCERTAIN"
    duplicate = "DUPLICATE"
    other = "OTHER"


class ProspectCommercialLossReason(StrEnum):
    no_response = "NO_RESPONSE"
    not_interested = "NOT_INTERESTED"
    no_budget = "NO_BUDGET"
    existing_provider = "EXISTING_PROVIDER"
    problem_not_perceived = "PROBLEM_NOT_PERCEIVED"
    timing = "TIMING"
    wrong_contact = "WRONG_CONTACT"
    price = "PRICE"
    offer_unclear = "OFFER_UNCLEAR"
    other = "OTHER"


class StageAQualification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    active_real_business: int = Field(ge=0, le=2)
    website_commercial_importance: int = Field(ge=0, le=2)
    business_economic_value: int = Field(ge=0, le=2)
    business_size_fit: int = Field(ge=0, le=2)
    decision_maker_reachability: int = Field(ge=0, le=2)
    website_manageability: int = Field(ge=0, le=2)
    no_existing_web_team: int = Field(ge=0, le=2)
    reason: str = Field(min_length=1, max_length=1000)
    rejection_reason: ProspectRejectionReason | None = None

    @property
    def score(self) -> int:
        return sum(
            (
                self.active_real_business,
                self.website_commercial_importance,
                self.business_economic_value,
                self.business_size_fit,
                self.decision_maker_reachability,
                self.website_manageability,
                self.no_existing_web_team,
            )
        )

    @property
    def decision(self) -> ProspectDecision:
        if self.rejection_reason is not None:
            return ProspectDecision.reject
        if self.score >= 11:
            return ProspectDecision.send_to_audit
        if self.score >= 8:
            return ProspectDecision.hold
        return ProspectDecision.reject


class Prospect(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    business_name: str = Field(min_length=1, max_length=200)
    website: HttpUrl | None = None
    sector: str = Field(default="", max_length=120)
    locality: str = Field(default="", max_length=120)
    administrative_area: str = Field(default="", max_length=120)
    country_code: str = Field(default="", max_length=2)
    phone: str = Field(default="", max_length=80)
    contact_name: str = Field(default="", max_length=160)
    contact_email: str = Field(default="", max_length=254)
    provider: str = Field(default="manual", max_length=80)
    provider_key: str = Field(default="", max_length=240)
    source_url: HttpUrl | None = None
    evidence_summary: str = Field(default="", max_length=4000)
    qualification: StageAQualification | None = None
    status: ProspectStatus = ProspectStatus.needs_review
    audit_project_id: str = Field(default="", max_length=24)
    best_observation: str = Field(default="", max_length=1000)
    webify_fixable: bool | None = None
    estimated_effort_hours: float | None = Field(default=None, ge=0, le=10_000)
    likely_offer: str = Field(default="", max_length=240)
    outreach_offer: str = Field(default="", max_length=240)
    message_variant: str = Field(default="", max_length=120)
    commercial_loss_reason: ProspectCommercialLossReason | None = None
    commercial_note: str = Field(default="", max_length=2000)
    human_verified: bool = False
    rejection_reason: ProspectRejectionReason | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def align_terminal_reasons(self) -> Prospect:
        if self.status is ProspectStatus.unsuitable and self.rejection_reason is None:
            raise ValueError("Unsuitable prospects require a rejection reason.")
        if self.status is ProspectStatus.lost and self.commercial_loss_reason is None:
            raise ValueError("Lost prospects require a commercial loss reason.")
        return self


class ProspectStoreError(RuntimeError):
    pass


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


def prospect_identifier(prospect: Prospect) -> str:
    website = str(prospect.website or "").lower().rstrip("/")
    canonical = "|".join(
        (
            prospect.business_name.casefold(),
            website,
            prospect.locality.casefold(),
            prospect.country_code.casefold(),
        )
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


class ProspectStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def save(self, prospect: Prospect) -> str:
        identifier = prospect_identifier(prospect)
        content = json.dumps(
            prospect.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        _atomic_write(self.directory / f"{identifier}.json", content)
        return identifier

    def load(self, prospect_id: str) -> Prospect:
        path = self.directory / f"{prospect_id}.json"
        try:
            return Prospect.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ProspectStoreError("Saved prospect was not found or is invalid.") from exc

    def list(self, *, status: ProspectStatus | None = None) -> list[tuple[str, Prospect]]:
        if not self.directory.exists():
            return []
        items: list[tuple[str, Prospect]] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                prospect = Prospect.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if status is None or prospect.status is status:
                items.append((path.stem, prospect))
        return sorted(items, key=lambda item: (item[1].updated_at, item[0]), reverse=True)

    def replace(self, prospect_id: str, prospect: Prospect) -> None:
        path = self.directory / f"{prospect_id}.json"
        if not path.exists():
            raise ProspectStoreError("Saved prospect was not found.")
        if prospect_identifier(prospect) != prospect_id:
            raise ProspectStoreError("Prospect identity fields cannot be changed in place.")
        content = json.dumps(
            prospect.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        _atomic_write(path, content)

    def delete(self, prospect_id: str) -> None:
        path = self.directory / f"{prospect_id}.json"
        if not path.exists():
            raise ProspectStoreError("Saved prospect was not found.")
        path.unlink()
