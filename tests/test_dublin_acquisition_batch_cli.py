from __future__ import annotations

import json
import zipfile
from pathlib import Path

from veridra.dublin_acquisition_batch_cli import (
    _historical_identities,
    _identity,
    _normalise_website,
)


def test_normalise_website_removes_tracking_only() -> None:
    value = _normalise_website(
        "HTTPS://Clinic.IE/contact/?utm_source=google&ref=maps#top"
    )
    assert value == "https://clinic.ie/contact?ref=maps"


def test_identity_uses_provider_key_and_normalised_website() -> None:
    row: dict[str, object] = {
        "business": {
            "provider_key": "maps:abc",
            "website": "https://clinic.ie/?utm_campaign=x",
        }
    }
    assert _identity(row) == ("maps:abc", "https://clinic.ie/")


def test_historical_identities_reads_prior_discovery_zips(tmp_path: Path) -> None:
    path = tmp_path / "VERIDRA_DISCOVERY_old.zip"
    rows = [
        {
            "business": {
                "provider_key": "maps:one",
                "website": "https://one.ie/?utm_source=maps",
            }
        },
        {
            "business": {
                "provider_key": "maps:two",
                "website": "https://two.ie/",
            }
        },
    ]
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("captured_observations.json", json.dumps(rows))

    keys, websites, count = _historical_identities(tmp_path)
    assert count == 2
    assert keys == {"maps:one", "maps:two"}
    assert websites == {"https://one.ie/", "https://two.ie/"}
