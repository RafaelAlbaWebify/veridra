# ruff: noqa: I001
"""Synthetic first-customer Playwright acceptance on the canonical Webify local runtime."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import operator_e2e_acceptance as base
import sales_contract_acceptance as sales
from playwright.sync_api import sync_playwright

from veridra.local_operator_bootstrap import ensure_local_operator



def _manual_assessment_local(page, project_url: str) -> str:
    """Handle canonical project navigation without legacy disclosure widgets."""
    page.goto(project_url, wait_until="networkidle")
    page.get_by_role("button", name="Run first assessment").click()
    page.wait_for_url("**/agency/projects/*?assessment_id=*", timeout=120_000)
    page.wait_for_load_state("networkidle", timeout=120_000)
    base._assert_text(page, "Saved assessment", timeout=120_000)
    monitoring = page.locator("a[href$='/monitoring']").first
    if monitoring.count() == 0:
        raise AssertionError("Canonical project page has no monitoring link.")
    monitoring.click()
    page.wait_for_url("**/monitoring")
    page.wait_for_load_state("networkidle")
    base._assert_text(page, "Latest assessment")
    return page.url


def _report_local(page, project_url: str, evidence: Path) -> None:
    """Verify report generation through canonical project navigation."""
    page.goto(project_url, wait_until="networkidle")
    page.locator("a[href$='/reports']").first.click()
    page.wait_for_load_state("networkidle")
    page.get_by_role("link", name="Create or change report profile").click()
    page.wait_for_load_state("networkidle")
    page.get_by_label("Organisation").fill("Webify Digital Solutions")
    page.get_by_label("Client").fill(base.BUSINESS)
    page.get_by_label("Cover title").fill("E2E Digital Presence Review")
    page.get_by_role("textbox", name="Executive summary", exact=True).fill(
        "Synthetic local E2E assessment report."
    )
    page.get_by_label("Accent colour").fill("#123456")
    page.get_by_role("button", name="Create and apply profile").click()
    page.wait_for_url("**/reports?profile=created")
    page.get_by_role("link", name="Preview branded HTML").click()
    page.wait_for_load_state("networkidle")
    base._assert_text(page, "Webify Digital Solutions")
    page.go_back(wait_until="networkidle")
    # A failed PDF response does not create a Playwright download event.
    # Inspect the authenticated HTTP response instead to report the real error.
    pdf_url = page.get_by_role("link", name="Download PDF").get_attribute("href")
    if not pdf_url:
        raise AssertionError("Canonical report has no PDF download link.")
    response = page.request.get(pdf_url, timeout=90_000)
    if response.status != 200:
        raise AssertionError(
            f"Canonical PDF generation returned HTTP {response.status}: "
            + response.text()[:400]
        )
    content = response.body()
    pdf = evidence / "local-first-customer-report.pdf"
    pdf.write_bytes(content)
    if not content.startswith(b"%PDF-") or len(content) < 1000:
        raise AssertionError("Canonical local branded PDF is invalid.")
    page.get_by_role("link", name="Email PDF via configured SMTP").click()
    page.get_by_label("Recipient").fill("acceptance@example.com")
    page.get_by_label("Subject").fill("Synthetic Webify first-customer delivery")
    page.get_by_label("Message").fill("Local test capture only.")
    page.get_by_role("button", name="Send PDF report").click()
    page.wait_for_url("**/reports?delivery=delivered")
    base._assert_text(page, "SMTP accepted the report delivery")

def run() -> None:
    repo = Path(__file__).resolve().parents[1]
    output = repo / "artifacts" / "local-first-customer-acceptance"
    output.mkdir(parents=True, exist_ok=True)
    checks: dict[str, bool] = {}
    with tempfile.TemporaryDirectory(prefix="veridra-local-first-customer-") as tmp:
        localapp = Path(tmp) / "LocalAppData"
        localapp.mkdir()
        port = base._free_port()
        origin = f"http://127.0.0.1:{port}"
        data = localapp / "VeridraCommercial" / "data"
        ensure_local_operator(data / "identity" / "veridra.sqlite3", data / "tenants")
        capture_dir = Path(tmp) / "email-captures"
        capture_dir.mkdir()
        env = {k: v for k, v in os.environ.items() if not k.startswith("VERIDRA_")}
        env.update({
            "LOCALAPPDATA": str(localapp),
            "VERIDRA_ACCEPTANCE_PROFILE": "local",
            "VERIDRA_LOCAL_PORT": str(port),
            "VERIDRA_OUTREACH_PRIVACY_URL": "https://webify.example/privacy",
            "VERIDRA_SMTP_HOST": "capture.invalid",
            "VERIDRA_SMTP_SENDER": "acceptance@example.com",
            "VERIDRA_REPORT_EMAIL_CAPTURE_DIR": str(capture_dir),
        })
        runtime = localapp / "VeridraCommercial" / "runtime"
        backup_dir = localapp / "VeridraCommercial" / "backups"
        started = False
        try:
            sales._launcher(repo, env, "start")
            started = True
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1440, "height": 1000})
                page = context.new_page()
                page.set_default_timeout(20000)
                page.goto(f"{origin}/agency", wait_until="domcontentloaded")
                base._assert_text(page, "WEBIFY · VERIDRA LOCAL")
                checks["canonical_local_started"] = True

                prospect_url = base._create_and_qualify_prospect(page, origin)
                checks["prospect_qualified"] = True
                for stage in ("contacted", "responded", "conversation"):
                    base._commercial_stage(
                        page, prospect_url, stage,
                        f"Synthetic {stage} stage; no external communication.",
                    )
                base._create_and_accept_proposal(page, prospect_url)
                checks["proposal_accepted"] = True

                customer_url = base._open_customer(page, origin)
                base._open_work_start_gate(page, customer_url)
                base._complete_onboarding(page, customer_url)
                checks["customer_onboarded"] = True

                project_url = base._create_linked_project(page, customer_url)
                monitoring_url = _manual_assessment_local(page, project_url)
                base._remediation(page, project_url)
                checks["project_and_remediation"] = True

                _report_local(page, project_url, output)
                captures = list(capture_dir.glob("report-*.eml"))
                if len(captures) != 1:
                    raise AssertionError(
                        f"Expected one synthetic report email, got {len(captures)}."
                    )
                checks["report_pdf_and_local_capture"] = True

                base._configure_autonomous_monitoring(page, monitoring_url)
                monitor_log = runtime / "veridra-commercial-monitoring.stdout.log"
                base._wait_autonomous_monitoring(monitor_log, page, monitoring_url)
                checks["autonomous_monitoring"] = True

                base._billing(page, customer_url, base.BILLING_NOTE)
                sales._launcher(repo, env, "restart")
                page.goto(customer_url, wait_until="networkidle")
                base._assert_text(page, "Billing: Paid")
                checks["restart_persistence"] = True

                sales._launcher(repo, env, "backup")
                backups = sorted(backup_dir.glob("VERIDRA_COMMERCIAL_BACKUP_*.zip"))
                if len(backups) != 1:
                    raise AssertionError("Expected a single synthetic commercial backup.")
                sales._launcher(repo, env, "recovery-test")
                checks["isolated_recovery"] = True
                context.close()
                browser.close()
        finally:
            if started:
                sales._launcher(repo, env, "stop")
            if runtime.exists():
                for path in runtime.glob("*.log"):
                    shutil.copy2(path, output / path.name)

    report = {
        "contract": "canonical_local_first_customer",
        "created_at": datetime.now(UTC).isoformat(),
        "checks": checks,
        "passed": len(checks) == 9 and all(checks.values()),
    }
    (output / "acceptance.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    if not report["passed"]:
        raise AssertionError(f"Incomplete first-customer acceptance: {report}")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    run()
