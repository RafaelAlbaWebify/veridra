from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .core import Assessment, UnsafeTargetError, resolve_public_ips
from .lead_store import AuditLead, JsonModelStore, LeadFormConfig, default_lead_directory

_MAX_PAYLOAD_BYTES = 64_000
_TIMEOUT_SECONDS = 5.0


class DeliveryStatus(StrEnum):
    delivered = "delivered"
    failed = "failed"


class LeadDeliveryAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lead_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    form_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    webhook_url: str = Field(min_length=1, max_length=2048)
    attempted_at: datetime
    status: DeliveryStatus
    attempt_number: int = Field(ge=1, le=1000)
    status_code: int | None = Field(default=None, ge=100, le=599)
    error: str = Field(default="", max_length=500)
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class LeadDeliveryStore(JsonModelStore):
    def __init__(self, directory: Path | None = None) -> None:
        super().__init__(directory or default_lead_directory() / "deliveries", LeadDeliveryAttempt)

    def list_for_lead(self, lead_id: str) -> list[tuple[str, LeadDeliveryAttempt]]:
        attempts = [
            (identifier, LeadDeliveryAttempt.model_validate(model))
            for identifier, model in super().list()
        ]
        return sorted(
            (item for item in attempts if item[1].lead_id == lead_id),
            key=lambda item: (item[1].attempted_at, item[1].attempt_number, item[0]),
            reverse=True,
        )


def build_lead_payload(
    lead_id: str,
    lead: AuditLead,
    assessment: Assessment,
) -> bytes:
    payload: dict[str, Any] = {
        "event": "lead.created",
        "lead": {
            "id": lead_id,
            "form_id": lead.form_id,
            "website": str(lead.website),
            "name": lead.name,
            "email": str(lead.email),
            "company": lead.company,
            "phone": lead.phone,
            "status": lead.status.value,
            "consented_at": lead.consented_at.isoformat(),
            "consent_text": lead.consent_text,
            "assessment_id": lead.assessment_id,
        },
        "assessment": {
            "target": str(assessment.target),
            "generated_at": assessment.generated_at.isoformat(),
            "summary": assessment.summary,
            "area_summary": assessment.area_summary,
        },
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    if len(encoded) > _MAX_PAYLOAD_BYTES:
        raise ValueError("Lead webhook payload exceeds the delivery size limit.")
    return encoded


def signature_header(payload: bytes, secret: str | None) -> str | None:
    if not secret:
        return None
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def validate_webhook_destination(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise UnsafeTargetError("Lead webhooks require an HTTPS URL with a hostname.")
    if parsed.username or parsed.password:
        raise UnsafeTargetError("Credentials in webhook URLs are not allowed.")
    resolve_public_ips(parsed.hostname)
    return parsed._replace(fragment="").geturl()


async def deliver_lead_webhook(
    *,
    lead_id: str,
    lead: AuditLead,
    assessment: Assessment,
    config: LeadFormConfig,
    store: LeadDeliveryStore | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> LeadDeliveryAttempt | None:
    if config.webhook_url is None:
        return None

    active_store = store or LeadDeliveryStore()
    previous = active_store.list_for_lead(lead_id)
    attempt_number = len(previous) + 1
    payload = build_lead_payload(lead_id, lead, assessment)
    digest = hashlib.sha256(payload).hexdigest()
    attempted_at = datetime.now(UTC)
    webhook_url = str(config.webhook_url)

    try:
        destination = validate_webhook_destination(webhook_url)
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Veridra-Lead-Webhook/2.9",
            "X-Veridra-Event": "lead.created",
            "X-Veridra-Delivery": f"{lead_id}-{attempt_number}",
        }
        signature = signature_header(payload, config.webhook_secret)
        if signature is not None:
            headers["X-Veridra-Signature"] = signature
        async with httpx.AsyncClient(
            timeout=_TIMEOUT_SECONDS,
            follow_redirects=False,
            transport=transport,
        ) as client:
            response = await client.post(destination, content=payload, headers=headers)
        if 200 <= response.status_code < 300:
            attempt = LeadDeliveryAttempt(
                lead_id=lead_id,
                form_id=lead.form_id,
                webhook_url=destination,
                attempted_at=attempted_at,
                status=DeliveryStatus.delivered,
                attempt_number=attempt_number,
                status_code=response.status_code,
                payload_sha256=digest,
            )
        else:
            attempt = LeadDeliveryAttempt(
                lead_id=lead_id,
                form_id=lead.form_id,
                webhook_url=destination,
                attempted_at=attempted_at,
                status=DeliveryStatus.failed,
                attempt_number=attempt_number,
                status_code=response.status_code,
                error="Webhook returned a non-success status.",
                payload_sha256=digest,
            )
    except (UnsafeTargetError, httpx.HTTPError, ValueError) as exc:
        attempt = LeadDeliveryAttempt(
            lead_id=lead_id,
            form_id=lead.form_id,
            webhook_url=webhook_url,
            attempted_at=attempted_at,
            status=DeliveryStatus.failed,
            attempt_number=attempt_number,
            error=str(exc)[:500],
            payload_sha256=digest,
        )

    active_store.save(attempt)
    return attempt
