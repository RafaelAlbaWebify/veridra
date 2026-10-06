from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HOME = (ROOT / "src" / "veridra" / "agency_workflow_web.py").read_text(encoding="utf-8")
COMMERCIAL = (
    ROOT / "src" / "veridra" / "agency_commercial_dashboard_web.py"
).read_text(encoding="utf-8")
DISCOVERY = (
    ROOT / "src" / "veridra" / "agency_prospect_discovery_web.py"
).read_text(encoding="utf-8")
IMPORT = (
    ROOT / "src" / "veridra" / "agency_prospect_import_web.py"
).read_text(encoding="utf-8")
TASKS = (ROOT / "src" / "veridra" / "agency_task_web.py").read_text(encoding="utf-8")


def test_agency_home_variants_use_internal_workbench_scroll() -> None:
    assert HOME.count("agency-workbench") >= 3
    assert HOME.count("workbench-scroll") >= 3


def test_commercial_dashboard_uses_fixed_header_and_internal_scroll() -> None:
    assert "class='agency-workbench'" in COMMERCIAL
    assert "class='workbench-head'" in COMMERCIAL
    assert "class='workbench-scroll'" in COMMERCIAL


def test_discovery_main_waiting_and_review_use_workbench() -> None:
    assert DISCOVERY.count("class='agency-workbench'") >= 3
    assert DISCOVERY.count("class='workbench-scroll'") >= 3


def test_import_uses_internal_workbench_scroll() -> None:
    assert "class='agency-workbench'" in IMPORT
    assert "class='workbench-scroll'" in IMPORT


def test_findings_and_task_confirmation_use_workbench() -> None:
    assert TASKS.count("class='agency-workbench'") >= 2
    assert "class='workbench-scroll'" in TASKS
    assert "class='workbench-pane'" in TASKS
