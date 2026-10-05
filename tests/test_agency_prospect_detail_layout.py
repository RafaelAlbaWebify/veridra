from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "src" / "veridra" / "agency_prospect_web.py").read_text(
    encoding="utf-8"
)


def test_prospect_detail_prioritizes_qualification_then_audit() -> None:
    assert "1. Qualification" in SCRIPT
    assert "2. Prospect audit" in SCRIPT
    assert "3. Outreach eligibility" in SCRIPT
    assert "4. Commercial progress" in SCRIPT
    assert "5. Activity history" in SCRIPT


def test_unscored_prospect_opens_qualification_but_keeps_later_stages_collapsed() -> None:
    assert 'qualification_open = " open" if qualification is None else ""' in SCRIPT
    assert (
        "<details class='disclosure compact-disclosure'>"
        "<summary>3. Outreach eligibility"
    ) in SCRIPT
    assert "4. Commercial progress <span class='summary-note'>Locked</span>" in SCRIPT


def test_prospect_detail_removes_duplicate_back_navigation() -> None:
    assert "← Prospects" not in SCRIPT
    assert "class='prospect-head'" in SCRIPT
    assert "class='prospect-meta'" in SCRIPT
