from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source(name: str) -> str:
    return (ROOT / "src" / "veridra" / name).read_text(encoding="utf-8")


def test_prospect_empty_states_offer_discovery_or_filter_reset() -> None:
    source = _source("agency_prospect_web.py")
    assert "No prospects yet." in source
    assert "href='/agency/prospects/discover'>Find prospects</a>" in source
    assert "href='/agency/prospects/new'>add a prospect manually</a>" in source
    assert "No prospects match the current filters." in source
    assert "href='/agency/prospects'>Reset filters</a>" in source


def test_customer_and_sales_empty_states_point_back_to_pipeline() -> None:
    customers = _source("agency_customer_web.py")
    deals = _source("agency_deal_index_web.py")
    assert "No customers yet." in customers
    assert "href='/agency/deals'>Open Sales / proposals</a>" in customers
    assert "No prospects are ready for Sales / proposals yet." in deals
    assert "href='/agency/prospects/discover'>Find prospects</a>" in deals


def test_presence_care_empty_state_points_to_eligible_projects() -> None:
    source = _source("agency_recurring_service_web.py")
    assert "No Presence Care services configured yet." in source
    assert (
        "Presence Care becomes available from eligible client projects after delivery and handoff."
        in source
    )
    assert "href='/agency/projects'>Open client projects</a>" in source


def test_remediation_empty_filter_has_reset_and_project_exit() -> None:
    source = _source("agency_task_management_web.py")
    assert "No remediation tasks match this view." in source
    assert "Show all tasks</a>" in source
    assert "return to the project</a>" in source
