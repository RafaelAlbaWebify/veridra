from __future__ import annotations

import json
from pathlib import Path

import pytest

from veridra.website_verification import (
    WebsiteVerificationStatus,
    load_website_verifications,
)


def test_loads_found_absent_and_inconclusive_verifications(tmp_path: Path) -> None:
    path = tmp_path / "verifications.json"
    path.write_text(
        json.dumps(
            [
                {
                    "business_name": "Found Dental",
                    "status": "website_found",
                    "website_url": "https://found.example",
                    "evidence_urls": ["https://source.example/found"],
                },
                {
                    "business_name": "Absent Dental",
                    "status": "absence_verified",
                    "evidence_urls": ["https://source.example/absent"],
                    "note": "Independent check found no official site.",
                },
                {
                    "business_name": "Maybe Dental",
                    "status": "inconclusive",
                },
            ]
        ),
        encoding="utf-8",
    )

    result = load_website_verifications(path)

    assert result["found dental"].status is WebsiteVerificationStatus.website_found
    assert result["found dental"].website_url == "https://found.example"
    assert result["absent dental"].status is WebsiteVerificationStatus.absence_verified
    assert result["absent dental"].website_url is None
    assert result["maybe dental"].status is WebsiteVerificationStatus.inconclusive


def test_website_found_requires_url(tmp_path: Path) -> None:
    path = tmp_path / "verifications.json"
    path.write_text(
        json.dumps([{"business_name": "Found Dental", "status": "website_found"}]),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="website_found requires website_url"):
        load_website_verifications(path)


def test_absence_verified_rejects_url(tmp_path: Path) -> None:
    path = tmp_path / "verifications.json"
    path.write_text(
        json.dumps(
            [
                {
                    "business_name": "Absent Dental",
                    "status": "absence_verified",
                    "website_url": "https://should-not-exist.example",
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="absence_verified cannot include website_url"):
        load_website_verifications(path)
