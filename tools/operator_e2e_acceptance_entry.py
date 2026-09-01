from __future__ import annotations

import os
import subprocess
import tempfile
import uuid
from pathlib import Path

import operator_e2e_acceptance as acceptance
from playwright.sync_api import Page


def _run_launcher(repo: Path, env: dict[str, str], command: str, *args: str) -> str:
    """Run the Windows launcher without PIPE handles inherited by long-lived children."""
    script = repo / "scripts" / "windows" / "veridra-local.ps1"
    print(f"[E2E] launcher {command}: start", flush=True)

    # Long-lived VERIDRA child processes can briefly retain inherited Windows file
    # handles after PowerShell exits. Keep launcher logs in the system temp directory
    # instead of synchronously deleting a TemporaryDirectory and racing those handles.
    output_path = (
        Path(tempfile.gettempdir())
        / f"veridra-launcher-{uuid.uuid4().hex}-{command}.log"
    )
    with output_path.open("w+", encoding="utf-8") as output:
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
            stdout=output,
            stderr=subprocess.STDOUT,
            timeout=180,
            check=False,
        )
        output.flush()
        output.seek(0)
        text = output.read()

    print(f"[E2E] launcher {command}: exit {completed.returncode}", flush=True)
    if text:
        print(text.rstrip(), flush=True)
    if completed.returncode != 0:
        raise RuntimeError(
            f"VERIDRA launcher {command!r} failed ({completed.returncode}):\n{text}"
        )
    return text


def _create_and_qualify_prospect(page: Page, base_url: str) -> str:
    """Use stable form names where visible labels are not HTML-associated controls."""
    page.goto(f"{base_url}/agency/prospects/new", wait_until="networkidle")
    values = {
        "business_name": acceptance.BUSINESS,
        "website": acceptance.TARGET,
        "sector": "Dental clinic",
        "phone": "+35315550100",
        "locality": "Dublin",
        "administrative_area": "Dublin",
        "country_code": "IE",
        "contact_email": "acceptance@example.com",
        "evidence_summary": (
            "Synthetic first-customer E2E evidence. No real business or outreach."
        ),
    }
    for name, value in values.items():
        page.locator(f"[name='{name}']").fill(value)
    page.get_by_role("button", name="Create prospect").click()
    page.wait_for_url("**/agency/prospects/*")
    prospect_url = page.url
    acceptance._assert_text(page, acceptance.BUSINESS)

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
    page.locator("textarea[name='reason']").fill(
        "Synthetic acceptance prospect intentionally qualifies for the operator workflow."
    )
    page.get_by_role("button", name="Save qualification").click()
    page.wait_for_url(prospect_url)
    page.wait_for_load_state("networkidle")
    acceptance._assert_text(page, "14/14")
    return prospect_url


def _report(page: Page, project_url: str, evidence: Path) -> None:
    """Exercise the real PDF control and validate the same authenticated PDF endpoint."""
    page.goto(project_url, wait_until="networkidle")
    page.get_by_role("link", name="Prepare branded report").click()
    page.wait_for_load_state("networkidle")
    page.get_by_role("link", name="Create or change report profile").click()
    page.wait_for_load_state("networkidle")
    page.get_by_label("Organisation").fill("Webify Digital Solutions")
    page.get_by_label("Client").fill(acceptance.BUSINESS)
    page.get_by_label("Cover title").fill("E2E Digital Presence Review")
    page.get_by_role("textbox", name="Executive summary", exact=True).fill(
        "Synthetic E2E assessment report."
    )
    page.get_by_label("Accent colour").fill("#123456")
    page.get_by_role("button", name="Create and apply profile").click()
    page.wait_for_url("**/reports?profile=created")
    page.get_by_role("link", name="Preview branded HTML").click()
    page.wait_for_load_state("networkidle")
    acceptance._assert_text(page, "Webify Digital Solutions")
    acceptance._assert_text(page, acceptance.BUSINESS)
    page.go_back(wait_until="networkidle")

    pdf_link = page.get_by_role("link", name="Download PDF")
    href = pdf_link.get_attribute("href")
    if not href:
        raise AssertionError("Download PDF link did not expose an href.")

    with page.expect_response(
        lambda response: response.url.endswith("/report.pdf"),
        timeout=90_000,
    ) as response_info:
        pdf_link.click()
    response = response_info.value
    if response.status != 200:
        raise AssertionError(f"Branded report PDF returned HTTP {response.status}.")
    disposition = response.headers.get("content-disposition", "")
    content_type = response.headers.get("content-type", "")
    if "attachment" not in disposition.lower() or "application/pdf" not in content_type.lower():
        raise AssertionError("Download PDF browser response was not a PDF attachment.")

    # Chromium may consume an attachment before CDP exposes its response body. Re-fetch
    # the exact href through the same authenticated browser context to validate bytes.
    pdf_response = page.context.request.get(href)
    if pdf_response.status != 200:
        raise AssertionError(
            f"Authenticated branded report fetch returned HTTP {pdf_response.status}."
        )
    content = pdf_response.body()
    if not content.startswith(b"%PDF-") or len(content) < 1000:
        raise AssertionError("Branded report response is not a valid non-empty PDF.")
    (evidence / "VERIDRA_E2E_REPORT.pdf").write_bytes(content)

    page.get_by_role("link", name="Email PDF report").click()
    page.get_by_label("Recipient").fill("acceptance@example.com")
    page.get_by_label("Subject").fill("VERIDRA E2E report delivery")
    page.get_by_label("Message").fill("Synthetic local capture only.")
    page.get_by_role("button", name="Send PDF report").click()
    page.wait_for_url("**/reports?delivery=delivered")
    acceptance._assert_text(page, "SMTP accepted the report delivery")


def _preserve_playwright_browser_cache() -> None:
    """Keep E2E state isolated without hiding Chromium installed by setup."""
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return
    localapp = os.environ.get("LOCALAPPDATA")
    if not localapp:
        return
    browser_cache = Path(localapp) / "ms-playwright"
    if browser_cache.exists():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_cache.resolve())
        print(f"[E2E] Reusing Playwright browser cache: {browser_cache}", flush=True)


acceptance._run_launcher = _run_launcher
acceptance._create_and_qualify_prospect = _create_and_qualify_prospect
acceptance._report = _report


if __name__ == "__main__":
    _preserve_playwright_browser_cache()
    acceptance.main()
