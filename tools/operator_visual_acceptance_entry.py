# ruff: noqa: I001
from __future__ import annotations

import json
import shutil
from pathlib import Path

import operator_e2e_acceptance as acceptance
import operator_e2e_acceptance_entry as hardened
from playwright.sync_api import Page


VISUAL_ROOT = Path("artifacts/operator-visual")
VISUAL_ROOT.mkdir(parents=True, exist_ok=True)


def _capture(page: Page, name: str) -> None:
    """Capture a full-page screenshot plus operator-visible text for visual review."""
    VISUAL_ROOT.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(VISUAL_ROOT / f"{name}.png"), full_page=True)
    visible = page.locator("body").inner_text(timeout=10_000)
    (VISUAL_ROOT / f"{name}.txt").write_text(visible, encoding="utf-8")


_ORIGINAL_ONBOARD = acceptance._onboard
_ORIGINAL_ENABLE_PLAN = acceptance._enable_agency_plan
_ORIGINAL_CREATE_AND_QUALIFY = acceptance._create_and_qualify_prospect
_ORIGINAL_COMMERCIAL_STAGE = acceptance._commercial_stage
_ORIGINAL_OPEN_CUSTOMER = acceptance._open_customer
_ORIGINAL_COMPLETE_ONBOARDING = acceptance._complete_onboarding
_ORIGINAL_CREATE_LINKED_PROJECT = acceptance._create_linked_project
_ORIGINAL_MANUAL_ASSESSMENT = acceptance._manual_assessment
_ORIGINAL_REMEDIATION = acceptance._remediation
_ORIGINAL_REPORT = acceptance._report
_ORIGINAL_CONFIGURE_MONITORING = acceptance._configure_autonomous_monitoring
_ORIGINAL_WAIT_MONITORING = acceptance._wait_autonomous_monitoring
_ORIGINAL_BILLING = acceptance._billing


def _onboard(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/onboarding", wait_until="networkidle")
    _capture(page, "01-onboarding-empty")
    _ORIGINAL_ONBOARD(page, base_url)
    _capture(page, "02-agency-home-after-onboarding")


def _enable_agency_plan(page: Page, base_url: str) -> None:
    _ORIGINAL_ENABLE_PLAN(page, base_url)
    _capture(page, "03-workspace-agency-plan")


def _create_and_qualify_prospect(page: Page, base_url: str) -> str:
    page.goto(f"{base_url}/agency/prospects/new", wait_until="networkidle")
    _capture(page, "04-new-prospect-form")
    prospect_url = _ORIGINAL_CREATE_AND_QUALIFY(page, base_url)
    _capture(page, "05-qualified-prospect")
    return prospect_url


def _commercial_stage(page: Page, prospect_url: str, stage: str, note: str) -> None:
    _ORIGINAL_COMMERCIAL_STAGE(page, prospect_url, stage, note)
    _capture(page, f"06-commercial-{stage}")


def _open_customer(page: Page, base_url: str) -> str:
    customer_url = _ORIGINAL_OPEN_CUSTOMER(page, base_url)
    _capture(page, "07-customer-created")
    return customer_url


def _complete_onboarding(page: Page, customer_url: str) -> None:
    _ORIGINAL_COMPLETE_ONBOARDING(page, customer_url)
    _capture(page, "08-customer-onboarded")


def _create_linked_project(page: Page, customer_url: str) -> str:
    project_url = _ORIGINAL_CREATE_LINKED_PROJECT(page, customer_url)
    _capture(page, "09-linked-project")
    return project_url


def _manual_assessment(page: Page, project_url: str) -> str:
    monitoring_url = _ORIGINAL_MANUAL_ASSESSMENT(page, project_url)
    _capture(page, "10-monitoring-after-assessment")
    result_url = f"{project_url}/ai-review/results/review-e2e-standard-exchange"
    page.goto(result_url, wait_until="networkidle")
    acceptance._assert_text(
        page,
        "AI interpretation — imported reasoning, not VERIDRA observation",
    )
    _capture(page, "11-ai-review-imported-result")
    page.goto(monitoring_url, wait_until="networkidle")
    return monitoring_url


def _remediation(page: Page, project_url: str) -> None:
    _ORIGINAL_REMEDIATION(page, project_url)
    _capture(page, "12-remediation-task")


def _report(page: Page, project_url: str, evidence: Path) -> None:
    _ORIGINAL_REPORT(page, project_url, evidence)
    _capture(page, "13-report-delivery-status")
    report_pdf = evidence / "VERIDRA_E2E_REPORT.pdf"
    if report_pdf.exists():
        shutil.copy2(report_pdf, VISUAL_ROOT / "VERIDRA_E2E_REPORT.pdf")
        (VISUAL_ROOT / "report-path.json").write_text(
            json.dumps({"report_pdf": str(report_pdf)}, indent=2),
            encoding="utf-8",
        )


def _configure_autonomous_monitoring(page: Page, monitoring_url: str) -> None:
    _ORIGINAL_CONFIGURE_MONITORING(page, monitoring_url)
    _capture(page, "14-monitoring-configured")


def _wait_autonomous_monitoring(runtime_log: Path, page: Page, monitoring_url: str) -> None:
    _ORIGINAL_WAIT_MONITORING(runtime_log, page, monitoring_url)
    _capture(page, "15-progress-changes")


def _billing(page: Page, customer_url: str, note: str) -> None:
    _ORIGINAL_BILLING(page, customer_url, note)
    _capture(page, "16-customer-billing")


acceptance._onboard = _onboard
acceptance._enable_agency_plan = _enable_agency_plan
acceptance._create_and_qualify_prospect = _create_and_qualify_prospect
acceptance._commercial_stage = _commercial_stage
acceptance._open_customer = _open_customer
acceptance._complete_onboarding = _complete_onboarding
acceptance._create_linked_project = _create_linked_project
acceptance._manual_assessment = _manual_assessment
acceptance._remediation = _remediation
acceptance._report = _report
acceptance._configure_autonomous_monitoring = _configure_autonomous_monitoring
acceptance._wait_autonomous_monitoring = _wait_autonomous_monitoring
acceptance._billing = _billing


if __name__ == "__main__":
    hardened._preserve_playwright_browser_cache()
    acceptance.main()
