from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from veridra.core import Assessment, UnsafeTargetError, demo_assessment
from veridra.lead_delivery import (
    DeliveryStatus,
    LeadDeliveryStore,
    build_lead_payload,
    deliver_lead_webhook,
    signature_header,
    validate_webhook_destination,
)
from veridra.lead_store import AuditLead, LeadFormConfig

_FORM_ID = "a" * 24
_LEAD_ID = "b" * 24
_ASSESSMENT_ID = "c" * 24


def _lead() -> AuditLead:
    return AuditLead(
        form_id=_FORM_ID,
        website="https://example.com/",
        name="Rafael",
        email="rafael@example.com",
        company="Example Co",
        phone="+34 600 000 000",
        consent_text="I agree to be contacted.",
        consented_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
        assessment_id=_ASSESSMENT_ID,
    )


def test_payload_is_deterministic_and_bounded() -> None:
    assessment = demo_assessment()
    first = build_lead_payload(_LEAD_ID, _lead(), assessment)
    second = build_lead_payload(_LEAD_ID, _lead(), assessment)

    assert first == second
    payload = json.loads(first)
    assert payload["event"] == "lead.created"
    assert payload["lead"]["id"] == _LEAD_ID
    assert payload["assessment"]["summary"] == assessment.summary
    assert len(first) < 64_000


def test_signature_header_is_stable() -> None:
    payload = b'{"event":"lead.created"}'
    assert signature_header(payload, None) is None
    assert signature_header(payload, "0123456789abcdef") == (
        "sha256=7f57c42b436b882190023575a7ce4a2dfd5f9ad2fda65c14c922f70c6775df31"
    )


def test_destination_requires_https_and_public_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("veridra.lead_delivery.resolve_public_ips", lambda hostname: ["203.0.113.10"])
    assert validate_webhook_destination("https://hooks.example.test/path#fragment") == (
        "https://hooks.example.test/path"
    )
    with pytest.raises(UnsafeTargetError):
        validate_webhook_destination("http://hooks.example.test/path")
    with pytest.raises(UnsafeTargetError):
        validate_webhook_destination("https://user:pass@hooks.example.test/path")


@pytest.mark.asyncio
async def test_successful_signed_delivery_is_persisted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("veridra.lead_delivery.resolve_public_ips", lambda hostname: ["203.0.113.10"])
    observed: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        observed["signature"] = request.headers["X-Veridra-Signature"]
        observed["digest"] = hashlib.sha256(body).hexdigest()
        observed["event"] = request.headers["X-Veridra-Event"]
        return httpx.Response(204)

    store = LeadDeliveryStore(tmp_path)
    config = LeadFormConfig(
        organisation_label="Agency",
        consent_text="I agree.",
        webhook_url="https://hooks.example.test/veridra",
        webhook_secret="0123456789abcdef",
    )
    attempt = await deliver_lead_webhook(
        lead_id=_LEAD_ID,
        lead=_lead(),
        assessment=demo_assessment(),
        config=config,
        store=store,
        transport=httpx.MockTransport(handler),
    )

    assert attempt is not None
    assert attempt.status == DeliveryStatus.delivered
    assert attempt.status_code == 204
    assert attempt.payload_sha256 == observed["digest"]
    assert observed["signature"].startswith("sha256=")
    assert observed["event"] == "lead.created"
    assert store.list_for_lead(_LEAD_ID)[0][1] == attempt


@pytest.mark.asyncio
async def test_failed_delivery_is_recorded_without_raising(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "veridra.lead_delivery.resolve_public_ips",
        lambda hostname: (_ for _ in ()).throw(UnsafeTargetError("Private destination blocked.")),
    )
    config = LeadFormConfig(
        organisation_label="Agency",
        consent_text="I agree.",
        webhook_url="https://internal.example.test/hook",
    )
    store = LeadDeliveryStore(tmp_path)

    attempt = await deliver_lead_webhook(
        lead_id=_LEAD_ID,
        lead=_lead(),
        assessment=Assessment.model_validate(demo_assessment()),
        config=config,
        store=store,
    )

    assert attempt is not None
    assert attempt.status == DeliveryStatus.failed
    assert attempt.status_code is None
    assert "Private destination blocked" in attempt.error
    assert len(store.list_for_lead(_LEAD_ID)) == 1


def test_webhook_configuration_validation() -> None:
    with pytest.raises(ValueError):
        LeadFormConfig(
            organisation_label="Agency",
            consent_text="I agree.",
            webhook_url="http://example.com/hook",
        )
    with pytest.raises(ValueError):
        LeadFormConfig(
            organisation_label="Agency",
            consent_text="I agree.",
            webhook_secret="0123456789abcdef",
        )
