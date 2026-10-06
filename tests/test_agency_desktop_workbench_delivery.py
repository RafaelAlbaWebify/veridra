from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CONVERSION = (ROOT / "src" / "veridra" / "agency_conversion_web.py").read_text(
    encoding="utf-8"
)
DELIVERY = (ROOT / "src" / "veridra" / "agency_project_customer_web.py").read_text(
    encoding="utf-8"
)
TASKS = (ROOT / "src" / "veridra" / "agency_task_management_web.py").read_text(
    encoding="utf-8"
)
MONITORING = (ROOT / "src" / "veridra" / "agency_monitoring_web.py").read_text(
    encoding="utf-8"
)
REPORTS = (ROOT / "src" / "veridra" / "agency_report_web.py").read_text(
    encoding="utf-8"
)


def test_project_overview_and_delivery_use_workbench() -> None:
    assert "class='agency-workbench'" in CONVERSION
    assert "class='workbench-head'" in CONVERSION
    assert "class='agency-workbench'" in DELIVERY
    assert "class='workbench-scroll'" in DELIVERY


def test_tasks_use_fixed_headers_and_internal_scroll() -> None:
    assert TASKS.count("class='agency-workbench'") >= 2
    assert "class='workbench-scroll'" in TASKS


def test_monitoring_uses_split_workbench_and_comparison_scroll() -> None:
    assert "class='workbench-split'" in MONITORING
    assert "class='workbench-scroll'" in MONITORING
    assert "Assessment comparison for" in MONITORING


def test_reports_use_split_workbench() -> None:
    assert "class='agency-workbench'" in REPORTS
    assert "class='workbench-split'" in REPORTS
    assert "Optional SMTP delivery history" in REPORTS
