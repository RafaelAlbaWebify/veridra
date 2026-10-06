from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

AI = (ROOT / "src" / "veridra" / "agency_ai_review_web.py").read_text(encoding="utf-8")
CHANGES = (ROOT / "src" / "veridra" / "agency_change_request_web.py").read_text(encoding="utf-8")
CRAWL = (ROOT / "src" / "veridra" / "agency_crawl_profile_web.py").read_text(encoding="utf-8")
PROGRESS = (ROOT / "src" / "veridra" / "agency_progress_web.py").read_text(encoding="utf-8")
PROFILE = (ROOT / "src" / "veridra" / "agency_report_profile_web.py").read_text(encoding="utf-8")
PROFILE_EDIT = (
    ROOT / "src" / "veridra" / "agency_report_profile_edit_web.py"
).read_text(encoding="utf-8")


def test_ai_review_surfaces_use_workbench() -> None:
    assert AI.count("class='agency-workbench'") >= 3
    assert "class='workbench-scroll'" in AI
    assert "class='workbench-split'" in AI


def test_scope_changes_use_split_workbench() -> None:
    assert "class='agency-workbench'" in CHANGES
    assert "class='workbench-split'" in CHANGES


def test_crawl_profile_uses_split_workbench() -> None:
    assert "class='agency-workbench'" in CRAWL
    assert "class='workbench-split'" in CRAWL


def test_progress_uses_fixed_header_and_internal_scroll() -> None:
    assert "class='agency-workbench'" in PROGRESS
    assert "class='workbench-scroll'" in PROGRESS


def test_report_profile_surfaces_use_internal_scroll() -> None:
    assert "class='agency-workbench'" in PROFILE
    assert "class='workbench-scroll'" in PROFILE
    assert "class='agency-workbench'" in PROFILE_EDIT
    assert "class='workbench-scroll'" in PROFILE_EDIT
