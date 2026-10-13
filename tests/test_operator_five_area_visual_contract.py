"""Contract checks for the read-only operator visual evidence runner."""
from __future__ import annotations

from pathlib import Path
from runpy import run_path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "operator_five_area_visual.py"
_TOOL = run_path(str(_SCRIPT))


def test_visual_evidence_has_exact_canonical_five_areas() -> None:
    areas = _TOOL["AREAS"]
    assert [item[1] for item in areas] == [
        "/agency/prospects", "/agency/deals", "/agency/customers",
        "/agency/projects", "/agency/recurring-services",
    ]
    assert len({item[0] for item in areas}) == 5


@pytest.mark.parametrize("url", [
    "https://127.0.0.1:8010", "http://example.com:8010",
    "http://127.0.0.1:8010/?token=x", "http://127.0.0.1:8010/agency",
    "http://user:secret@127.0.0.1:8010",
])
def test_visual_evidence_rejects_nonlocal_or_nonroot_urls(
    url: str, tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="loopback"):
        _TOOL["capture"](url, tmp_path / "no-files")
    assert not (tmp_path / "no-files").exists()
