from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "src" / "veridra" / "agency_prospect_discovery_web.py").read_text(
    encoding="utf-8"
)


def test_review_selection_actions_are_unambiguous() -> None:
    assert "Apply selection" not in SCRIPT
    assert "Select all rows" in SCRIPT
    assert "Clear selection" in SCRIPT
    assert "Ingest selected opportunities" in SCRIPT
    assert "Select rows individually below" in SCRIPT


def test_review_not_found_is_rendered_as_recoverable_html() -> None:
    assert "Discovery review unavailable" in SCRIPT
    assert "Start new discovery" in SCRIPT
    assert "completed reviews created after this update persist across VERIDRA restarts" in SCRIPT
