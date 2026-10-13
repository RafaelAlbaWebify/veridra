"""Prevent regressions in operator visual evidence ZIP packaging."""
from __future__ import annotations

from pathlib import Path

from tools.market_operator_live_readonly import evidence_result, evidence_zip_path


def test_evidence_result_keeps_verified_count_across_tabs() -> None:
    result = evidence_result(445)
    assert result["result"] == "PASS"
    assert result["business_count"] == 445
    assert result["map_tiles"] == "not tested: external resources blocked"


def test_evidence_zip_default_uses_downloads(tmp_path: Path) -> None:
    assert evidence_zip_path(tmp_path).parent == tmp_path
    assert evidence_zip_path(tmp_path).name == "VERIDRA_MARKET_VISUAL_EVIDENCE.zip"
