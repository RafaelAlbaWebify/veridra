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
from urllib.parse import quote
from urllib.request import urlopen

from playwright.sync_api import Page, sync_playwright

OUTPUT_ROOT = Path("artifacts/commercial-acceptance")
PASSWORD = "veridra-commercial-acceptance"
ACCEPTANCE_BRAND = "Acceptance Agency"
ACCEPTANCE_COVER_TITLE = "Demo SMB Website Review"
ACCEPTANCE_SUMMARY = "Acceptance-authored executive summary."


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
    page.get_by_label("Executive summary").fill(ACCEPTANCE_SUMMARY)
    page.get_by_label("Accent colour").fill("#123456")
    page.get_by_role("button", name="Create and apply profile").click()
    page.wait_for_url("**/reports?profile=created")
    page.wait_for_load_state("networkidle")


def _verify_branded_report(
    page: Page,
    output: Path,
    report: dict[str, object],
) -> None:
    checks = report.setdefault("checks", {})
    if not isinstance(checks, dict):
        raise RuntimeError("Commercial acceptance checks must be a mapping.")

    checks["profile_created"] = ACCEPTANCE_BRAND in page.locator("main").inner_text()
    report["steps"].append(_capture(page, output, "04-branded-report-hub"))

    page.get_by_role("link", name="Preview branded HTML").click()
    page.wait_for_load_state("networkidle")
    body_text = page.locator("body").inner_text()
    checks["html_brand_visible"] = ACCEPTANCE_BRAND in body_text
    checks["html_cover_title_visible"] = ACCEPTANCE_COVER_TITLE in body_text
    checks["html_summary_visible"] = ACCEPTANCE_SUMMARY in body_text
    report["steps"].append(_capture(page, output, "05-branded-report-preview"))

    page.go_back(wait_until="networkidle")
    with page.expect_download() as download_info:
        page.get_by_role("link", name="Download PDF").click()
    download = download_info.value
    filename = download.suggested_filename
    pdf_path = output / filename
    download.save_as(pdf_path)
    pdf_content = pdf_path.read_bytes()
    checks["pdf_filename_branded"] = (
        filename.startswith("acceptance-agency-") and not filename.startswith("veridra-")
    )
    checks["pdf_signature_valid"] = pdf_content.startswith(b"%PDF-") and len(pdf_content) > 1000
    report["pdf"] = {"filename": filename, "bytes": len(pdf_content)}


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
                    report["steps"].append(_capture(page, run_dir, "01-agency-home"))

                    if target:
                        _run_real_quick_audit(page, base_url, target)
                        report["steps"].append(_capture(page, run_dir, "02-real-quick-audit"))
                    else:
                        _create_demo_project(page, base_url)
                        project_url = page.url
                        report["steps"].append(_capture(page, run_dir, "02-project-overview"))
                        _configure_branded_report(page)
                        report["steps"].append(_capture(page, run_dir, "03-report-profile-created"))
                        _verify_branded_report(page, run_dir, report)
                        page.goto(project_url, wait_until="networkidle")
                        page.get_by_role("link", name="Enable monitoring").click()
                        page.wait_for_load_state("networkidle")
                        report["steps"].append(_capture(page, run_dir, "06-monitoring"))
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
