from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class WebsiteVerificationStatus(StrEnum):
    website_found = "website_found"
    absence_verified = "absence_verified"
    inconclusive = "inconclusive"


@dataclass(frozen=True, slots=True)
class WebsiteVerification:
    business_name: str
    status: WebsiteVerificationStatus
    website_url: str | None
    evidence_urls: tuple[str, ...]
    note: str | None


def load_website_verifications(path: Path) -> dict[str, WebsiteVerification]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Website verification file must contain a JSON list.")

    result: dict[str, WebsiteVerification] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("business_name")
        status_raw = item.get("status")
        if not isinstance(name, str) or not name.strip() or not isinstance(status_raw, str):
            continue
        try:
            status = WebsiteVerificationStatus(status_raw)
        except ValueError:
            continue
        website_url_raw = item.get("website_url")
        website_url = website_url_raw.strip() if isinstance(website_url_raw, str) else None
        urls_raw = item.get("evidence_urls")
        evidence_urls = (
            tuple(value.strip() for value in urls_raw if isinstance(value, str) and value.strip())
            if isinstance(urls_raw, list)
            else ()
        )
        note_raw = item.get("note")
        note = note_raw.strip() if isinstance(note_raw, str) and note_raw.strip() else None

        if status is WebsiteVerificationStatus.website_found and not website_url:
            raise ValueError(f"website_found requires website_url for {name.strip()}")
        if status is WebsiteVerificationStatus.absence_verified and website_url:
            raise ValueError(f"absence_verified cannot include website_url for {name.strip()}")

        result[name.strip().casefold()] = WebsiteVerification(
            business_name=name.strip(),
            status=status,
            website_url=website_url,
            evidence_urls=evidence_urls,
            note=note,
        )
    return result
