from __future__ import annotations

import subprocess
import tempfile
import uuid
from pathlib import Path

from playwright.sync_api import Page

import operator_e2e_acceptance as acceptance


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


acceptance._run_launcher = _run_launcher
acceptance._create_and_qualify_prospect = _create_and_qualify_prospect


if __name__ == "__main__":
    acceptance.main()
