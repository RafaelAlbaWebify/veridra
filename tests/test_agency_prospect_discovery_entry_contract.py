from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "src" / "veridra" / "agency_prospect_discovery_web.py").read_text(
    encoding="utf-8"
)


def test_discovery_entry_has_no_demo_search_prefill_or_duplicate_back_link() -> None:
    assert "value='dentist'" not in SCRIPT
    assert "value='Dublin, Ireland'" not in SCRIPT
    assert "← Prospects" not in SCRIPT
    assert "id='advanced-options'" in SCRIPT
    assert "<details class='advanced' id='advanced-options'>" in SCRIPT
