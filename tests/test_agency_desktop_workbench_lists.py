from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

NAV = (ROOT / "src" / "veridra" / "agency_navigation.py").read_text(encoding="utf-8")
PROSPECTS = (ROOT / "src" / "veridra" / "agency_prospect_web.py").read_text(encoding="utf-8")
DEALS = (ROOT / "src" / "veridra" / "agency_deal_index_web.py").read_text(encoding="utf-8")
LEADS = (ROOT / "src" / "veridra" / "agency_lead_web.py").read_text(encoding="utf-8")
CUSTOMERS = (ROOT / "src" / "veridra" / "agency_customer_web.py").read_text(encoding="utf-8")
PROJECTS = (ROOT / "src" / "veridra" / "agency_project_index_web.py").read_text(encoding="utf-8")
RECURRING = (ROOT / "src" / "veridra" / "agency_recurring_service_web.py").read_text(
    encoding="utf-8"
)


def test_shared_desktop_workbench_keeps_page_fixed_and_content_scrollable() -> None:
    assert "body:has(.agency-workbench){overflow:hidden}" in NAV
    assert ".workbench-body" in NAV
    assert ".workbench-scroll" in NAV
    assert ".workbench-cards" in NAV
    assert "position:sticky" in NAV


def test_primary_operating_lists_use_shared_workbench() -> None:
    for source in (PROSPECTS, DEALS, LEADS, CUSTOMERS, PROJECTS, RECURRING):
        assert "agency-workbench" in source
        assert "workbench-head" in source
        assert "workbench-body" in source


def test_table_lists_use_internal_scroll_regions() -> None:
    for source in (PROSPECTS, DEALS, LEADS, RECURRING):
        assert "workbench-scroll" in source


def test_card_lists_use_internal_scroll_regions() -> None:
    for source in (CUSTOMERS, PROJECTS):
        assert "workbench-cards" in source


def test_presence_care_marks_its_own_navigation_item_current() -> None:
    assert "agency_navigation(identity, current='recurring')" in RECURRING
