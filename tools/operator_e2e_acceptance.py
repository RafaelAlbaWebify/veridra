from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

PASSWORD = "VeridraAcceptance271!"
WORKSPACE = "webify-e2e-271"
EMAIL = "operator@example.test"
BUSINESS = "VERIDRA E2E Dental"
PROJECT = "VERIDRA E2E Delivery"
TARGET = "https://example.com/"
OFFER = "Website Improvement Sprint"
COHORT = "e2e-271"
INVOICE = "WEB-E2E-271"
BILLING_NOTE = "E2E paid acceptance state."
MUTATED_BILLING_NOTE = "MUTATED AFTER BACKUP"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run_launcher(repo: Path, env: dict[str, str], command: str, *args: str) -> str:
    script = repo / "scripts" / "windows" / "veridra-local.ps1"
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            command,
            *args,
        ],
        cwd=repo,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=180,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"VERIDRA launcher {command!r} failed ({completed.returncode}):\n"
            f"{completed.stdout}"
        )
    return completed.stdout


def _shot(page: Page, evidence: Path, name: str) -> None:
    page.screenshot(path=str(evidence / f"{name}.png"), full_page=True)


def _step(report: dict[str, Any], page: Page, evidence: Path, name: str) -> None:
    _shot(page, evidence, name)
    report["steps"].append(
        {
            "name": name,
            "url": page.url,
            "title": page.title(),
        }
    )


def _assert_text(page: Page, text: str, *, timeout: int = 10_000) -> None:
    page.get_by_text(text, exact=False).first.wait_for(state="visible", timeout=timeout)


def _login(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/login", wait_until="networkidle")
    page.get_by_label("Workspace slug").fill(WORKSPACE)
    page.get_by_label("Email").fill(EMAIL)
    page.get_by_label("Password").fill(PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url(f"{base_url}/agency", timeout=15_000)


def _ensure_authenticated(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/agency", wait_until="networkidle")
    if "/login" in page.url:
        _login(page, base_url)


def _onboard(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/onboarding", wait_until="networkidle")
    page.get_by_label("Agency or organisation name").fill("Webify E2E Acceptance")
    page.get_by_label("Workspace slug").fill(WORKSPACE)
    page.get_by_label("Your name").fill("Acceptance Operator")
    page.get_by_label("Email").fill(EMAIL)
    page.get_by_label("Password", exact=True).fill(PASSWORD)
    page.get_by_label("Repeat password").fill(PASSWORD)
    page.get_by_role("button", name="Create agency workspace").click()
    page.wait_for_url(f"{base_url}/agency", timeout=15_000)


def _enable_agency_plan(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/workspace", wait_until="networkidle")
    page.locator("select[name='plan']").select_option("agency")
    page.get_by_role("button", name="Preview plan").click()
    page.wait_for_url("**/workspace/plan-preview?**")
    page.get_by_role("button", name="Apply local policy").click()
    page.wait_for_url(f"{base_url}/workspace")
    page.wait_for_load_state("networkidle")
    _assert_text(page, "Plan: Agency")


def _create_and_qualify_prospect(page: Page, base_url: str) -> str:
    page.goto(f"{base_url}/agency/prospects/new", wait_until="networkidle")
    page.get_by_label("Business name").fill(BUSINESS)
    page.get_by_label("Website").fill(TARGET)
    page.get_by_label("Sector").fill("Dental clinic")
    page.get_by_label("Phone").fill("+35315550100")
    page.get_by_label("Locality").fill("Dublin")
    page.get_by_label("Administrative area").fill("Dublin")
    page.get_by_label("Country code").fill("IE")
    page.get_by_label("Contact email").fill("acceptance@example.test")
    page.get_by_label("Evidence / discovery note").fill(
        "Synthetic first-customer E2E evidence. No real business or outreach."
    )
    page.get_by_role("button", name="Create prospect").click()
    page.wait_for_url("**/agency/prospects/*")
    prospect_url = page.url
    _assert_text(page, BUSINESS)

    for name in (
        "active_real_business",
        "website_commercial_importance",
        "business_economic_value",
        "business_size_fit",
        "decision_maker_reachability",
        "website_manageability",
        "no_existing_web_team",
    ):
        page.locator(f"select[name='{name}']").select_option("2")
    page.get_by_label("Why this score?").fill(
        "Synthetic acceptance prospect intentionally qualifies for the operator workflow."
    )
    page.get_by_role("button", name="Save qualification").click()
    page.wait_for_url(prospect_url)
    page.wait_for_load_state("networkidle")
    _assert_text(page, "14/14")
    return prospect_url


def _commercial_stage(page: Page, prospect_url: str, stage: str, note: str) -> None:
    page.goto(prospect_url, wait_until="networkidle")
    page.get_by_label("Funnel stage").select_option(stage)
    page.get_by_label("Offer used").fill(OFFER)
    page.get_by_label("Message variant / cohort").fill(COHORT)
    page.get_by_label("Next action").fill(f"E2E next action after {stage}")
    page.get_by_label("Commercial note").fill(note)
    page.get_by_role("button", name="Save commercial progress").click()
    page.wait_for_url(prospect_url)
    page.wait_for_load_state("networkidle")
    if page.get_by_label("Funnel stage").input_value() != stage:
        raise AssertionError(f"Commercial stage {stage!r} did not persist through the UI.")


def _open_customer(page: Page, base_url: str) -> str:
    page.goto(f"{base_url}/agency/customers", wait_until="networkidle")
    _assert_text(page, BUSINESS)
    page.get_by_role("link", name="Open customer").click()
    page.wait_for_url("**/agency/customers/*")
    return page.url


def _complete_onboarding(page: Page, customer_url: str) -> None:
    page.goto(customer_url, wait_until="networkidle")
    for label in (
        "Primary contact confirmed",
        "Service scope confirmed",
        "Commercial terms confirmed",
        "Access/domain/hosting requirements confirmed",
        "Kickoff completed",
    ):
        page.get_by_label(label).check()
    page.get_by_label("Customer status").select_option("active")
    page.get_by_label("Commercial / onboarding notes").fill(
        "Synthetic onboarding completed by Playwright acceptance."
    )
    page.get_by_role("button", name="Save customer").click()
    page.wait_for_url(customer_url)
    page.wait_for_load_state("networkidle")
    _assert_text(page, "Onboarding: 5/5")
    _assert_text(page, "Status: Active")


def _create_linked_project(page: Page, customer_url: str) -> str:
    page.goto(customer_url, wait_until="networkidle")
    page.get_by_label("Project name").fill(PROJECT)
    page.get_by_label("Delivery target URL").fill(TARGET)
    page.get_by_role("button", name="Create and link project").click()
    page.wait_for_url(customer_url)
    page.wait_for_load_state("networkidle")
    page.get_by_role("link", name=PROJECT).click()
    page.wait_for_url("**/agency/projects/*")
    project_url = page.url
    _assert_text(page, f"Customer: {BUSINESS}")
    return project_url


def _manual_assessment(page: Page, project_url: str) -> str:
    page.goto(project_url, wait_until="networkidle")
    page.get_by_role("link", name="Enable monitoring").click()
    page.wait_for_url("**/monitoring")
    monitoring_url = page.url
    page.get_by_role("button", name="Run monitoring now").click()
    page.wait_for_url("**/monitoring?**", timeout=120_000)
    page.wait_for_load_state("networkidle", timeout=120_000)
    _assert_text(page, "Assessment", timeout=120_000)
    if "assessment_id=" not in page.url:
        raise AssertionError("Manual monitoring run did not expose a saved assessment id.")
    return monitoring_url


def _remediation(page: Page, project_url: str) -> None:
    page.goto(project_url, wait_until="networkidle")
    page.get_by_role("link", name="Review saved findings").click()
    page.wait_for_load_state("networkidle")
    _assert_text(page, "findings")
    create_links = page.get_by_role("link", name="Create task")
    if create_links.count() < 1:
        raise AssertionError("Saved assessment exposed no finding that can create a remediation task.")
    create_links.first.click()
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Confirm task creation").click()
    page.wait_for_url("**/tasks?task_created=*")
    page.get_by_role("link", name="Open task").first.click()
    page.wait_for_load_state("networkidle")
    page.get_by_label("Status").select_option("in_progress")
    page.get_by_label("Owner").fill("Acceptance Operator")
    page.get_by_label("Due date").fill("2026-09-15")
    page.get_by_label("Notes").fill("E2E remediation task in progress.")
    page.get_by_role("button", name="Save task").click()
    page.wait_for_url("**/tasks")
    page.wait_for_load_state("networkidle")
    _assert_text(page, "Acceptance Operator")


def _report(page: Page, project_url: str, evidence: Path) -> None:
    page.goto(project_url, wait_until="networkidle")
    page.get_by_role("link", name="Prepare branded report").click()
    page.wait_for_load_state("networkidle")
    page.get_by_role("link", name="Create or change report profile").click()
    page.wait_for_load_state("networkidle")
    page.get_by_label("Organisation").fill("Webify Digital Solutions")
    page.get_by_label("Client").fill(BUSINESS)
    page.get_by_label("Cover title").fill("E2E Digital Presence Review")
    page.get_by_role("textbox", name="Executive summary", exact=True).fill(
        "Synthetic E2E assessment report."
    )
    page.get_by_label("Accent colour").fill("#123456")
    page.get_by_role("button", name="Create and apply profile").click()
    page.wait_for_url("**/reports?profile=created")
    page.get_by_role("link", name="Preview branded HTML").click()
    page.wait_for_load_state("networkidle")
    _assert_text(page, "Webify Digital Solutions")
    _assert_text(page, BUSINESS)
    page.go_back(wait_until="networkidle")
    with page.expect_download(timeout=90_000) as download_info:
        page.get_by_role("link", name="Download PDF").click()
    download = download_info.value
    pdf = evidence / download.suggested_filename
    download.save_as(pdf)
    content = pdf.read_bytes()
    if not content.startswith(b"%PDF-") or len(content) < 1000:
        raise AssertionError("Downloaded branded report is not a valid non-empty PDF.")

    page.get_by_role("link", name="Email PDF report").click()
    page.get_by_label("Recipient").fill("acceptance@example.test")
    page.get_by_label("Subject").fill("VERIDRA E2E report delivery")
    page.get_by_label("Message").fill("Synthetic local capture only.")
    page.get_by_role("button", name="Send PDF report").click()
    page.wait_for_url("**/reports?delivery=delivered")
    _assert_text(page, "SMTP accepted the report delivery")


def _configure_autonomous_monitoring(page: Page, monitoring_url: str) -> None:
    page.goto(monitoring_url, wait_until="networkidle")
    page.get_by_label("Cadence").select_option("daily")
    page.get_by_label("Timezone").fill("UTC")
    now = datetime.now(UTC)
    page.get_by_label("Hour").fill(str(now.hour))
    page.get_by_label("Minute").fill(str(now.minute))
    page.get_by_label("Notification email").fill("")
    page.get_by_role("button", name="Save monitoring configuration").click()
    page.wait_for_url("**/monitoring?saved=true")
    _assert_text(page, "Monitoring configuration saved")


def _wait_autonomous_monitoring(runtime_log: Path, page: Page, monitoring_url: str) -> None:
    deadline = time.monotonic() + 100
    saw_job = False
    while time.monotonic() < deadline:
        if runtime_log.exists():
            text = runtime_log.read_text(encoding="utf-8", errors="replace")
            if re.search(r"jobs_enqueued=[1-9]\d*.*succeeded=[1-9]\d*", text):
                saw_job = True
                break
        time.sleep(2)
    if not saw_job:
        text = runtime_log.read_text(encoding="utf-8", errors="replace") if runtime_log.exists() else ""
        raise AssertionError(f"Autonomous monitoring service did not complete a due run.\n{text}")
    page.goto(monitoring_url, wait_until="networkidle")
    _assert_text(page, "Latest assessment")
    _assert_text(page, "Previous assessment")


def _billing(page: Page, customer_url: str, note: str) -> None:
    page.goto(customer_url, wait_until="networkidle")
    page.get_by_label("Billing status").select_option("paid")
    page.get_by_label("Invoice reference").fill(INVOICE)
    page.get_by_label("Invoice amount").fill("650.00")
    page.get_by_label("Currency").fill("EUR")
    page.get_by_label("Issued on").fill("2026-08-31")
    page.get_by_label("Due on").fill("2026-09-14")
    page.get_by_label("Billing note").fill(note)
    page.get_by_role("button", name="Save customer").click()
    page.wait_for_url(customer_url)
    page.wait_for_load_state("networkidle")
    _assert_text(page, "Billing: Paid")
    if page.get_by_label("Billing note").input_value() != note:
        raise AssertionError("Billing note did not persist.")


def _dashboard(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/agency/commercial", wait_until="networkidle")
    _assert_text(page, "Commercial dashboard")
    _assert_text(page, "Active customers")
    _assert_text(page, "Paid customers")
    _assert_text(page, "EUR 650.00")


def _copy_runtime_evidence(state_root: Path, evidence: Path) -> None:
    runtime = state_root / "Veridra" / "runtime"
    if not runtime.exists():
        return
    for source in runtime.glob("*.log"):
        shutil.copy2(source, evidence / source.name)


def run() -> Path:
    if os.name != "nt":
        raise SystemExit("Operator E2E acceptance must run on Windows.")
    repo = Path(__file__).resolve().parents[1]
    downloads = Path.home() / "Downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_zip = downloads / f"VERIDRA_OPERATOR_E2E_ACCEPTANCE_{stamp}.zip"

    report: dict[str, Any] = {
        "contract": "veridra_operator_e2e_acceptance",
        "version": "1.0",
        "started_at": datetime.now(UTC).isoformat(),
        "passed": False,
        "steps": [],
        "checks": {},
    }

    with tempfile.TemporaryDirectory(prefix="veridra-e2e-271-") as temporary:
        temp = Path(temporary)
        fake_localapp = temp / "LocalAppData"
        capture_dir = temp / "captured-report-email"
        evidence = temp / "evidence"
        fake_localapp.mkdir(parents=True)
        capture_dir.mkdir(parents=True)
        evidence.mkdir(parents=True)
        port = _free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["LOCALAPPDATA"] = str(fake_localapp)
        env["VERIDRA_LOCAL_PORT"] = str(port)
        env["VERIDRA_REPORT_EMAIL_CAPTURE_DIR"] = str(capture_dir.resolve())

        state_root = fake_localapp
        monitoring_log = state_root / "Veridra" / "runtime" / "veridra-monitoring.stdout.log"
        backup_root = state_root / "Veridra" / "backups"

        try:
            _run_launcher(
                repo,
                env,
                "smtp-config",
                "-SmtpHost",
                "capture.invalid",
                "-SmtpPort",
                "587",
                "-SmtpSender",
                "acceptance@example.test",
                "-SmtpSenderName",
                "VERIDRA E2E",
            )
            _run_launcher(repo, env, "start")
            report["checks"]["supported_launcher_started"] = True

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1440, "height": 1000})
                page = context.new_page()

                _onboard(page, base_url)
                _enable_agency_plan(page, base_url)
                _step(report, page, evidence, "01-onboarded-agency")

                prospect_url = _create_and_qualify_prospect(page, base_url)
                report["checks"]["prospect_created_and_qualified_in_ui"] = True
                _step(report, page, evidence, "02-qualified-prospect")

                for index, stage in enumerate(
                    ("contacted", "responded", "conversation", "proposal", "customer"),
                    start=3,
                ):
                    _commercial_stage(
                        page,
                        prospect_url,
                        stage,
                        f"Synthetic E2E transition to {stage}; no outreach was sent.",
                    )
                    _step(report, page, evidence, f"{index:02d}-prospect-{stage}")
                report["checks"]["full_commercial_funnel_in_ui"] = True

                customer_url = _open_customer(page, base_url)
                _complete_onboarding(page, customer_url)
                _step(report, page, evidence, "08-customer-active-onboarded")
                report["checks"]["customer_created_and_onboarded_in_ui"] = True

                project_url = _create_linked_project(page, customer_url)
                _step(report, page, evidence, "09-linked-project")
                report["checks"]["customer_project_link_visible_both_directions"] = True

                monitoring_url = _manual_assessment(page, project_url)
                _step(report, page, evidence, "10-manual-assessment")
                report["checks"]["assessment_saved_via_ui"] = True

                _remediation(page, project_url)
                _step(report, page, evidence, "11-remediation-task")
                report["checks"]["remediation_managed_via_ui"] = True

                _report(page, project_url, evidence)
                _step(report, page, evidence, "12-report-delivery")
                captures = list(capture_dir.glob("report-*.eml"))
                if len(captures) != 1:
                    raise AssertionError(f"Expected one locally captured report email, got {len(captures)}.")
                shutil.copy2(captures[0], evidence / captures[0].name)
                report["checks"]["report_pdf_and_local_email_capture"] = True

                _configure_autonomous_monitoring(page, monitoring_url)
                _wait_autonomous_monitoring(monitoring_log, page, monitoring_url)
                _step(report, page, evidence, "13-autonomous-monitoring")
                report["checks"]["autonomous_monitoring_executed"] = True

                _billing(page, customer_url, BILLING_NOTE)
                _dashboard(page, base_url)
                _step(report, page, evidence, "14-paid-dashboard")
                report["checks"]["billing_and_dashboard_visible"] = True

                _run_launcher(repo, env, "restart")
                _ensure_authenticated(page, base_url)
                page.goto(customer_url, wait_until="networkidle")
                _assert_text(page, "Status: Active")
                _assert_text(page, "Billing: Paid")
                if page.get_by_label("Billing note").input_value() != BILLING_NOTE:
                    raise AssertionError("State did not survive supported restart.")
                _step(report, page, evidence, "15-restart-persistence")
                report["checks"]["state_survived_supported_restart"] = True

                _run_launcher(repo, env, "backup")
                backups = sorted(backup_root.glob("VERIDRA_BACKUP_*.zip"), key=lambda p: p.stat().st_mtime)
                if not backups:
                    raise AssertionError("Supported launcher did not create a backup ZIP.")
                backup = backups[-1]
                report["backup"] = backup.name

                _billing(page, customer_url, MUTATED_BILLING_NOTE)
                _step(report, page, evidence, "16-mutated-after-backup")
                report["checks"]["post_backup_state_mutated_via_ui"] = True

                _run_launcher(repo, env, "restore", "-BackupPath", str(backup), "-Apply")
                _run_launcher(repo, env, "start")
                _ensure_authenticated(page, base_url)
                page.goto(customer_url, wait_until="networkidle")
                restored_note = page.get_by_label("Billing note").input_value()
                if restored_note != BILLING_NOTE:
                    raise AssertionError(
                        f"Restore did not recover pre-mutation state: {restored_note!r}."
                    )
                _assert_text(page, "Status: Active")
                _assert_text(page, "Billing: Paid")
                _step(report, page, evidence, "17-restored-state")
                report["checks"]["supported_backup_restore_visibly_recovered_state"] = True

                context.close()
                browser.close()

            report["passed"] = all(report["checks"].values())
        except Exception as exc:
            report["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                _run_launcher(repo, env, "stop")
            except Exception as stop_exc:
                report.setdefault("cleanup_errors", []).append(str(stop_exc))
            _copy_runtime_evidence(state_root, evidence)
            report["finished_at"] = datetime.now(UTC).isoformat()
            (evidence / "operator-e2e-report.json").write_text(
                json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(evidence.iterdir()):
                    archive.write(path, arcname=path.name)

    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    print(f"Evidence ZIP: {output_zip}")
    if not report["passed"]:
        raise SystemExit(1)
    return output_zip


def main() -> None:
    run()


if __name__ == "__main__":
    main()
