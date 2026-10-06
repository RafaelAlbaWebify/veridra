from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

NAV = (ROOT / "src" / "veridra" / "agency_navigation.py").read_text(encoding="utf-8")
LEADS = (ROOT / "src" / "veridra" / "agency_lead_web.py").read_text(encoding="utf-8")
CUSTOMERS = (ROOT / "src" / "veridra" / "agency_customer_web.py").read_text(encoding="utf-8")
DEALS = (ROOT / "src" / "veridra" / "agency_deal_web.py").read_text(encoding="utf-8")
FORMS = (ROOT / "src" / "veridra" / "agency_lead_form_web.py").read_text(encoding="utf-8")


def test_shared_split_pane_workbench_is_available() -> None:
    assert ".workbench-split" in NAV
    assert ".workbench-pane" in NAV


def test_lead_detail_uses_fixed_summary_and_split_panes() -> None:
    assert "class='agency-workbench'" in LEADS
    assert "class='workbench-head'" in LEADS
    assert "class='workbench-split'" in LEADS
    assert "class='workbench-pane'" in LEADS


def test_customer_detail_uses_fixed_summary_and_internal_scroll() -> None:
    assert "class='agency-workbench'" in CUSTOMERS
    assert "class='workbench-head'" in CUSTOMERS
    assert "class='workbench-body'" in CUSTOMERS
    assert "class='workbench-scroll'" in CUSTOMERS


def test_sales_workflow_uses_fixed_header_and_internal_scroll() -> None:
    assert "class='agency-workbench'" in DEALS
    assert "class='workbench-head'" in DEALS
    assert "class='workbench-scroll'" in DEALS


def test_lead_forms_use_split_pane_workbench() -> None:
    assert "class='agency-workbench'" in FORMS
    assert "class='workbench-split'" in FORMS
    assert "Saved tenant lead forms" in FORMS
