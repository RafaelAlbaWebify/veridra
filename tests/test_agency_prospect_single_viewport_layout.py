from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "src" / "veridra" / "agency_prospect_web.py").read_text(
    encoding="utf-8"
)


def test_desktop_prospect_workbench_uses_single_viewport_layout() -> None:
    assert "class='prospect-workbench'" in SCRIPT
    assert "class='stage-strip'" in SCRIPT
    assert "repeat(4,minmax(0,1fr))" in SCRIPT
    assert "@media(min-width:1200px) and (min-height:800px)" in SCRIPT
    assert "body{overflow:hidden}" in SCRIPT
    assert "height:calc(100vh - 36px)" in SCRIPT


def test_qualification_is_compacted_into_grid_and_footer() -> None:
    assert "qualification-panel" in SCRIPT
    assert "class='qualification-footer'" in SCRIPT
    assert "Why this score?" in SCRIPT
    assert "Rejection reason (optional)" in SCRIPT


def test_small_screens_fall_back_to_scrollable_vertical_layout() -> None:
    assert "@media(max-width:760px)" in SCRIPT
    assert "body{overflow:auto}" in SCRIPT
    assert "height:auto;overflow:visible" in SCRIPT
