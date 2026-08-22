from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .prospect import Prospect, ProspectStatus

LEADMAP_EXPORT_SCHEMA_VERSION = "1.1"


class LeadMapImportError(ValueError):
    pass


class LeadMapExportRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    business_id: str = Field(min_length=1, max_length=120)
    location_id: str = Field(min_length=1, max_length=120)
    business_name: str = Field(min_length=1, max_length=200)
    qualification_status: str = Field(default="needs_review", max_length=80)
    country_code: str = Field(default="", max_length=2)
    administrative_area: str = Field(default="", max_length=120)
    locality: str = Field(default="", max_length=120)
    postal_area: str = Field(default="", max_length=40)
    phone: str = Field(default="", max_length=80)
    website: str = Field(default="", max_length=2048)
    first_observed_at: datetime
    last_observed_at: datetime


class LeadMapExport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    exported_at: datetime
    records: list[LeadMapExportRecord]


_STATUS_MAP: dict[str, ProspectStatus] = {
    "new": ProspectStatus.new,
    "needs_review": ProspectStatus.needs_review,
    "qualified": ProspectStatus.qualified,
    "shortlisted": ProspectStatus.shortlisted,
    "sent_to_veridra": ProspectStatus.ready_for_audit,
    "veridra_reviewed": ProspectStatus.audited,
    "approved_for_outreach": ProspectStatus.approved_for_outreach,
    "contacted": ProspectStatus.contacted,
    "responded": ProspectStatus.responded,
    "conversation": ProspectStatus.conversation,
    "proposal": ProspectStatus.proposal,
    "customer": ProspectStatus.customer,
    "unsuitable": ProspectStatus.needs_review,
    "duplicate": ProspectStatus.duplicate,
    "archived": ProspectStatus.archived,
}


def parse_leadmap_export(payload: str | bytes | dict[str, Any]) -> LeadMapExport:
    try:
        export = (
            LeadMapExport.model_validate(payload)
            if isinstance(payload, dict)
            else LeadMapExport.model_validate_json(payload)
        )
    except ValueError as exc:
        raise LeadMapImportError("LEADS export could not be validated.") from exc
    if export.schema_version != LEADMAP_EXPORT_SCHEMA_VERSION:
        raise LeadMapImportError(
            f"Unsupported LEADS export schema version: {export.schema_version}."
        )
    return export


def prospect_from_leadmap(record: LeadMapExportRecord) -> Prospect:
    status = _STATUS_MAP.get(record.qualification_status, ProspectStatus.needs_review)
    provider_key = f"{record.business_id}:{record.location_id}"
    observed = (
        f"Imported from LEADS schema {LEADMAP_EXPORT_SCHEMA_VERSION}; "
        f"first observed {record.first_observed_at.isoformat()}, "
        f"last observed {record.last_observed_at.isoformat()}."
    )
    return Prospect.model_validate(
        {
            "business_name": record.business_name,
            "website": record.website or None,
            "locality": record.locality,
            "administrative_area": record.administrative_area,
            "country_code": record.country_code.upper(),
            "phone": record.phone,
            "provider": "leadmap-local",
            "provider_key": provider_key,
            "evidence_summary": observed,
            "status": status,
            "created_at": record.first_observed_at,
            "updated_at": record.last_observed_at,
        }
    )


def prospects_from_leadmap_export(payload: str | bytes | dict[str, Any]) -> list[Prospect]:
    export = parse_leadmap_export(payload)
    return [prospect_from_leadmap(record) for record in export.records]
