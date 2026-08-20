from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import urlopen

from playwright.sync_api import Page, sync_playwright

OUTPUT_ROOT = Path("artifacts/commercial-acceptance")
PASSWORD = "veridra-commercial-acceptance"
ACCEPTANCE_BRAND = "Acceptance Agency"
ACCEPTANCE_COVER_TITLE = "Demo SMB Website Review"
ACCEPTANCE_SUMMARY = "Acceptance-authored executive summary."
ACCEPTANCE_LEAD_NAME = "Acceptance Prospect"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_ready(base_url: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{base_url}/health", timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.25)
    raise RuntimeError("Veridra composed runtime did not become ready.")


def _capture(page: Page, output: Path, name: str) -> dict[str, object]:
    screenshot = output / f"{name}.png"
    html_file = output / f"{name}.html"
    page.screenshot(path=screenshot, full_page=True)
    html_file.write_text(page.content(), encoding="utf-8")
    return {
        "name": name,
        "url": page.url,
        "title": page.title(),
        "screenshot": screenshot.name,
        "html": html_file.name,
        "main_text": page.locator("main").inner_text() if page.locator("main").count() else "",
    }


def _checks(report: dict[str, object]) -> dict[str, object]:
    checks = report.setdefault("checks", {})
    if not isinstance(checks, dict):
        raise RuntimeError("Commercial acceptance checks must be a mapping.")
    return checks


def _steps(report: dict[str, object]) -> list[object]:
    steps = report.setdefault("steps", [])
    if not isinstance(steps, list):
        raise RuntimeError("Commercial acceptance steps must be a list.")
    return steps


def _onboard(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/onboarding", wait_until="networkidle")
    page.get_by_label("Agency or organisation name").fill("Webify Acceptance")
    page.get_by_label("Workspace slug").fill("webify-acceptance")
    page.get_by_label("Your name").fill("Acceptance Operator")
    page.get_by_label("Email").fill("acceptance@example.com")
    page.get_by_label("Password", exact=True).fill(PASSWORD)
    page.get_by_label("Repeat password").fill(PASSWORD)
    page.get_by_role("button", name="Create agency workspace").click()
    page.wait_for_url(f"{base_url}/agency")


def _enable_professional_plan(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/workspace", wait_until="networkidle")
    page.locator("select[name='plan']").select_option("professional")
    page.get_by_role("button", name="Preview plan").click()
    page.wait_for_url("**/workspace/plan-preview?**")
    page.get_by_role("button", name="Apply local policy").click()
    page.wait_for_url(f"{base_url}/workspace")
    page.wait_for_load_state("networkidle")


def _create_demo_project(page: Page, base_url: str) -> None:
    page.goto(
        f"{base_url}/agency/convert?demo=true&url={quote('https://example.com/', safe='')}",
        wait_until="networkidle",
    )
    page.get_by_label("Project name").fill("Commercial Acceptance Demo")
    page.get_by_label("Client label").fill("Demo SMB")
    page.get_by_label("Project crawl profile").select_option("standard")
    page.get_by_role("button", name="Create client project").click()
    page.wait_for_url("**/agency/projects/**")


def _configure_branded_report(page: Page) -> None:
    page.get_by_role("link", name="Prepare branded report").click()
    page.wait_for_load_state("networkidle")
    page.get_by_role("link", name="Create or change report profile").click()
    page.wait_for_load_state("networkidle")
    page.get_by_label("Organisation").fill(ACCEPTANCE_BRAND)
    page.get_by_label("Client").fill("Demo SMB")
    page.get_by_label("Cover title").fill(ACCEPTANCE_COVER_TITLE)
    page.get_by_role("textbox", name="Executive summary", exact=True).fill(ACCEPTANCE_SUMMARY)
    page.get_by_label("Accent colour").fill("#123456")
    page.get_by_role("button", name="Create and apply profile").click()
    page.wait_for_url("**/reports?profile=created")
    page.wait_for_load_state("networkidle")


def _verify_branded_report(
    page: Page,
    output: Path,
    report: dict[str, object],
) -> None:
    checks = _checks(report)
    steps = _steps(report)

    checks["profile_created"] = ACCEPTANCE_BRAND in page.locator("main").inner_text()
    steps.append(_capture(page, output, "04-branded-report-hub"))

    page.get_by_role("link", name="Preview branded HTML").click()
    page.wait_for_load_state("networkidle")
    body_text = page.locator("body").inner_text()
    checks["html_brand_visible"] = ACCEPTANCE_BRAND.casefold() in body_text.casefold()
    checks["html_cover_title_visible"] = ACCEPTANCE_COVER_TITLE in body_text
    checks["html_summary_visible"] = ACCEPTANCE_SUMMARY in body_text
    checks["html_veridra_not_visible"] = "Veridra" not in body_text
    steps.append(_capture(page, output, "05-branded-report-preview"))

    page.go_back(wait_until="networkidle")
    with page.expect_download(timeout=60_000) as download_info:
        page.get_by_role("link", name="Download PDF").click()
    download = download_info.value
    filename = download.suggested_filename
    pdf_path = output / filename
    download.save_as(pdf_path)
    pdf_content = pdf_path.read_bytes()
    checks["pdf_filename_branded"] = (
        filename.startswith("Acceptance-Agency-")
        and not filename.startswith("Veridra-")
    )
    checks["pdf_signature_valid"] = (
        pdf_content.startswith(b"%PDF-") and len(pdf_content) > 1000
    )
    report["pdf"] = {"filename": filename, "bytes": len(pdf_content)}

    events = report.get("events", {})
    if isinstance(events, dict):
        failures = events.get("request_failures", [])
        if isinstance(failures, list):
            events["request_failures"] = [
                failure
                for failure in failures
                if not (
                    isinstance(failure, str)
                    and "/report.pdf: net::ERR_ABORTED" in failure
                )
            ]


def _exercise_lead_form(
    page: Page,
    base_url: str,
    output: Path,
    report: dict[str, object],
) -> str:
    checks = _checks(report)
    steps = _steps(report)
    page.goto(f"{base_url}/agency/lead-forms", wait_until="networkidle")
    page.get_by_label("Organisation label").fill(ACCEPTANCE_BRAND)
    page.get_by_label("Public heading").fill("Get your acceptance website review")
    page.get_by_label("Required consent wording").fill(
        "I agree that Acceptance Agency may contact me about this website audit."
    )
    page.get_by_role("button", name="Create lead form").click()
    page.wait_for_url("**/agency/lead-forms?created=*")
    page.wait_for_load_state("networkidle")
    form_id = parse_qs(urlparse(page.url).query).get("created", [""])[0]
    checks["tenant_lead_form_created"] = len(form_id) == 24
    checks["tenant_lead_form_bound"] = (
        "Lead form created and tenant-bound."
        in page.locator("main").inner_text()
    )
    steps.append(_capture(page, output, "06-tenant-lead-form"))

    page.get_by_role("link", name="Preview").click()
    page.wait_for_load_state("networkidle")
    public_text = page.locator("main").inner_text()
    checks["lead_form_public_preview"] = (
        ACCEPTANCE_BRAND in public_text
        and "Get your acceptance website review" in public_text
        and "Website" in public_text
    )
    steps.append(_capture(page, output, "07-lead-form-preview"))
    return form_id


def _seed_tenant_lead_fixture(page: Page, form_id: str) -> str:
    payload = {
        "form_id": form_id,
        "website": "https://example.com/",
        "name": ACCEPTANCE_LEAD_NAME,
        "email": "prospect@example.com",
        "company": "Acceptance Prospect Ltd",
        "phone": "+34 600 000 000",
        "consent_text": "Acceptance fixture consent",
        "consented_at": "2026-08-20T10:00:00Z",
        "assessment_id": "c" * 24,
    }
    result = page.evaluate(
        """async (payload) => {
            const response = await fetch('/api/tenant/leads', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload),
            });
            return {status: response.status, body: await response.json()};
        }""",
        payload,
    )
    if not isinstance(result, dict) or result.get("status") != 201:
        raise RuntimeError(f"Could not seed tenant lead fixture: {result!r}")
    body = result.get("body")
    if not isinstance(body, dict):
        raise RuntimeError("Tenant lead fixture response was not a mapping.")
    lead_id = str(body.get("id", ""))
    if len(lead_id) != 24:
        raise RuntimeError("Tenant lead fixture did not return a valid lead ID.")
    return lead_id


def _exercise_lead_qualification(
    page: Page,
    base_url: str,
    lead_id: str,
    output: Path,
    report: dict[str, object],
) -> None:
    checks = _checks(report)
    steps = _steps(report)
    page.goto(f"{base_url}/agency/leads", wait_until="networkidle")
    checks["seeded_lead_visible"] = ACCEPTANCE_LEAD_NAME in page.locator("main").inner_text()
    page.get_by_role("link", name="Open lead").click()
    page.wait_for_url(f"{base_url}/agency/leads/{lead_id}")
    page.get_by_label("Status").select_option("qualified")
    page.get_by_label("Owner").fill("Acceptance Operator")
    page.get_by_label("Next action").fill("Send acceptance proposal")
    page.get_by_label("Notes").fill("Qualified in deterministic commercial acceptance.")
    page.get_by_role("button", name="Save lead").click()
    page.wait_for_url(f"{base_url}/agency/leads/{lead_id}")
    page.wait_for_load_state("networkidle")
    checks["lead_qualified_in_ui"] = (
        page.get_by_label("Status").input_value() == "qualified"
    )
    checks["lead_follow_up_saved"] = (
        page.get_by_label("Next action").input_value()
        == "Send acceptance proposal"
    )
    steps.append(_capture(page, output, "08-qualified-lead"))


def _exercise_remediation(
    page: Page,
    project_url: str,
    output: Path,
    report: dict[str, object],
) -> None:
    checks = _checks(report)
    steps = _steps(report)
    page.goto(project_url, wait_until="networkidle")
    page.get_by_role("link", name="Create remediation tasks").click()
    page.wait_for_load_state("networkidle")
    page.get_by_role("link", name="Create task").first.click()
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Confirm task creation").click()
    page.wait_for_url("**/agency/projects/**/tasks?task_created=*")
    page.wait_for_load_state("networkidle")
    checks["remediation_task_created"] = (
        "remediation tasks" in page.locator("main").inner_text().casefold()
    )
    steps.append(_capture(page, output, "09-remediation-task-list"))

    page.get_by_role("link", name="Open task").first.click()
    page.wait_for_load_state("networkidle")
    page.get_by_label("Status").select_option("in_progress")
    page.get_by_label("Owner").fill("Acceptance Operator")
    page.get_by_label("Due date").fill("2026-08-25")
    page.get_by_label("Notes").fill("Acceptance remediation work started.")
    page.get_by_role("button", name="Save task").click()
    page.wait_for_url("**/agency/projects/**/tasks")
    page.wait_for_load_state("networkidle")
    task_text = page.locator("main").inner_text()
    checks["remediation_task_managed"] = (
        "in progress" in task_text.casefold()
        and "Acceptance Operator" in task_text
        and "2026-08-25" in task_text
    )
    steps.append(_capture(page, output, "10-remediation-task-managed"))


def _run_real_quick_audit(page: Page, base_url: str, target: str) -> None:
    page.goto(f"{base_url}/agency", wait_until="networkidle")
    page.get_by_label("Public website").fill(target)
    page.get_by_role("button", name="Start quick audit").click()
    page.wait_for_url("**/agency/audit?**", timeout=90_000)
    page.wait_for_load_state("networkidle", timeout=90_000)


def run(target: str | None = None) -> Path:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    run_dir = OUTPUT_ROOT / time.strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    events: dict[str, list[str]] = {"console_errors": [], "request_failures": []}
    report: dict[str, object] = {
        "passed": False,
        "mode": "real-target" if target else "isolated-demo",
        "target": target,
        "base_url": base_url,
        "steps": [],
        "events": events,
        "checks": {},
    }

    with tempfile.TemporaryDirectory(prefix="veridra-commercial-") as temporary:
        state = Path(temporary)
        env = os.environ.copy()
        env.update(
            {
                "VERIDRA_ENV": "development",
                "VERIDRA_BIND_HOST": "127.0.0.1",
                "VERIDRA_BIND_PORT": str(port),
                "VERIDRA_ALLOWED_HOSTS": "127.0.0.1,localhost",
                "VERIDRA_TRUSTED_ORIGIN": base_url,
                "VERIDRA_IDENTITY_DB": str((state / "identity" / "veridra.sqlite3").resolve()),
                "VERIDRA_TENANT_DATA_ROOT": str((state / "tenants").resolve()),
            }
        )
        stdout_path = run_dir / "runtime.stdout.log"
        stderr_path = run_dir / "runtime.stderr.log"
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
            "w", encoding="utf-8"
        ) as stderr:
            process = subprocess.Popen(
                [sys.executable, "-m", "veridra.runtime"],
                env=env,
                stdout=stdout,
                stderr=stderr,
            )
            try:
                _wait_ready(base_url)
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch()
                    page = browser.new_page(viewport={"width": 1440, "height": 1000})
                    page.on(
                        "console",
                        lambda message: events["console_errors"].append(message.text)
                        if message.type == "error"
                        else None,
                    )
                    page.on(
                        "requestfailed",
                        lambda request: events["request_failures"].append(
                            f"{request.method} {request.url}: {request.failure}"
                        ),
                    )
                    _onboard(page, base_url)
                    _steps(report).append(_capture(page, run_dir, "01-agency-home"))

                    if target:
                        _run_real_quick_audit(page, base_url, target)
                        _steps(report).append(_capture(page, run_dir, "02-real-quick-audit"))
                    else:
                        _enable_professional_plan(page, base_url)
                        checks = _checks(report)
                        checks["professional_plan_enabled"] = (
                            "Plan: Professional" in page.locator("main").inner_text()
                        )
                        _create_demo_project(page, base_url)
                        project_url = page.url
                        _steps(report).append(_capture(page, run_dir, "02-project-overview"))
                        _configure_branded_report(page)
                        _steps(report).append(_capture(page, run_dir, "03-report-profile-created"))
                        _verify_branded_report(page, run_dir, report)

                        form_id = _exercise_lead_form(page, base_url, run_dir, report)
                        lead_id = _seed_tenant_lead_fixture(page, form_id)
                        _exercise_lead_qualification(
                            page,
                            base_url,
                            lead_id,
                            run_dir,
                            report,
                        )
                        _exercise_remediation(page, project_url, run_dir, report)

                        page.goto(project_url, wait_until="networkidle")
                        page.get_by_role("link", name="Enable monitoring").click()
                        page.wait_for_load_state("networkidle")
                        _steps(report).append(_capture(page, run_dir, "11-monitoring"))
                    browser.close()
                checks = report.get("checks", {})
                checks_passed = all(checks.values()) if checks else target is not None
                report["passed"] = not events["request_failures"] and checks_passed
            except Exception as exc:
                report["error"] = str(exc)
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()

    report_path = run_dir / "commercial-acceptance.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    archive = shutil.make_archive(str(run_dir), "zip", root_dir=run_dir)
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"Evidence bundle: {archive}")
    if not report["passed"]:
        raise SystemExit(1)
    return Path(archive)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run isolated Playwright acceptance against the composed Veridra runtime."
    )
    parser.add_argument(
        "--target",
        help=(
            "Optional real public website for the quick-audit path. "
            "Omit for isolated demo acceptance."
        ),
    )
    args = parser.parse_args()
    run(args.target)


if __name__ == "__main__":
    main()
