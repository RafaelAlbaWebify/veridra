from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class CommercialEligibilityStatus(StrEnum):
    eligible = "eligible"
    ineligible = "ineligible"
    review_required = "review_required"


@dataclass(frozen=True, slots=True)
class CommercialEligibility:
    business_name: str
    status: CommercialEligibilityStatus
    reason: str
    evidence_urls: tuple[str, ...]


def gate_opportunity_band(
    band: str,
    status: CommercialEligibilityStatus | None,
) -> str:
    if status is CommercialEligibilityStatus.ineligible:
        return "low"
    if status is CommercialEligibilityStatus.review_required and band in {"priority", "high"}:
        return "medium"
    return band


def load_commercial_eligibility(path: Path) -> dict[str, CommercialEligibility]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Commercial eligibility file must contain a JSON list.")

    result: dict[str, CommercialEligibility] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("business_name")
        status_raw = item.get("status")
        reason_raw = item.get("reason")
        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(status_raw, str)
            or not isinstance(reason_raw, str)
            or not reason_raw.strip()
        ):
            continue
        try:
            status = CommercialEligibilityStatus(status_raw)
        except ValueError:
            continue
        urls_raw = item.get("evidence_urls")
        evidence_urls = (
            tuple(value.strip() for value in urls_raw if isinstance(value, str) and value.strip())
            if isinstance(urls_raw, list)
            else ()
        )
        result[name.strip().casefold()] = CommercialEligibility(
            business_name=name.strip(),
            status=status,
            reason=reason_raw.strip(),
            evidence_urls=evidence_urls,
        )
    return result
