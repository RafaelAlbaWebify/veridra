from __future__ import annotations

import json
import os
import subprocess
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import operator_e2e_acceptance as acceptance
from playwright.sync_api import Page

from veridra.ai_review_exchange import result_integrity_hash


def _run_launcher(repo: Path, env: dict[str, str], command: str, *args: str) -> str:
    """Run the Windows launcher without PIPE handles inherited by long-lived children."""
    script = repo / "scripts" / "windows" / "veridra-local.ps1"
    print(f"[E2E] launcher {command}: start", flush=True)

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


def _complete_onboarding_with_booking_gate(page: Page, customer_url: str) -> None:
    """Prove commercial work stays blocked until terms and required payment are evidenced."""
    page.goto(customer_url, wait_until="networkidle")
    acceptance._assert_text(page, "Work blocked")
    acceptance._assert_text(page, "Capture accepted terms")
    if page.get_by_role("button", name="Create and link project").count() != 0:
        raise AssertionError("Delivery project creation was exposed while work gate was blocked.")

    page.get_by_label("Terms / agreement reference").fill("WEBIFY-MSA-E2E")
    page.get_by_label("Terms version").fill("2026-09")
    page.get_by_label("Accepted at").fill("2026-09-03T10:00")
    page.get_by_label("External signature reference").fill("SIGN-E2E-001")
    page.get_by_label("Acceptance evidence").fill(
        "Synthetic accepted-terms evidence for Playwright operator acceptance."
    )
    page.get_by_label("Billing status").select_option("partially_paid")
    page.get_by_label("External invoice reference").fill(acceptance.INVOICE)
    page.get_by_label("Invoice amount").fill("650.00")
    page.get_by_label("Currency").fill("EUR")
    page.get_by_label("Issued on").fill("2026-09-03")
    page.get_by_label("Due on").fill("2026-09-17")
    page.get_by_label("Deposit / upfront payment required before work").check()
    page.get_by_label("Required upfront amount").fill("325.00")
    page.get_by_label("Amount paid").fill("325.00")
    page.get_by_label("Payment evidence reference").fill("PAY-E2E-DEPOSIT-001")
    page.get_by_label("Payment method reference").fill("bank transfer")
    page.get_by_label("Provider transaction reference").fill("BANK-E2E-001")
    page.get_by_role("button", name="Save customer").click()
    page.wait_for_url(customer_url)
    page.wait_for_load_state("networkidle")
    acceptance._assert_text(page, "Work may start")
    page.get_by_role("button", name="Create and link project").wait_for(
        state="visible", timeout=10_000
    )

    _ORIGINAL_COMPLETE_ONBOARDING(page, customer_url)


def _manual_assessment(page: Page, project_url: str) -> str:
    """Run the established assessment, then prove the JSON AI exchange through the browser."""
    monitoring_url = _ORIGINAL_MANUAL_ASSESSMENT(page, project_url)
    page.goto(project_url, wait_until="networkidle")
    page.get_by_role("link", name="AI review exchange").click()
    page.wait_for_url("**/ai-review")
    acceptance._assert_text(page, "AI review exchange")

    with page.expect_download(timeout=30_000) as download_info:
        page.get_by_role("link", name="Export AI review JSON").click()
    download_path = download_info.value.path()
    if download_path is None:
        raise AssertionError(
            "AI review export did not produce a downloadable JSON artifact."
        )
    bundle = json.loads(Path(download_path).read_text(encoding="utf-8"))
    if bundle.get("exchange_type") != "veridra_ai_review_bundle":
        raise AssertionError(
            "AI review export did not contain the standard bundle contract."
        )
    evidence = bundle.get("evidence")
    refs = (
        [
            item.get("evidence_id")
            for item in evidence
            if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
        ]
        if isinstance(evidence, list)
        else []
    )
    if not refs:
        raise AssertionError("AI review export contained no traceable finding evidence.")

    result: dict[str, object] = {
        "schema_version": "1.0",
        "exchange_type": "veridra_ai_review_result",
        "review_id": "review-e2e-standard-exchange",
        "source_bundle_id": bundle["bundle_id"],
        "source_bundle_hash_sha256": bundle["bundle_hash_sha256"],
        "generated_at": datetime.now(UTC).isoformat(),
        "model_provenance": "synthetic-playwright-fixture",
        "tool_provenance": "VERIDRA operator E2E",
        "interpretation": (
            "Synthetic evidence-bound interpretation for operator acceptance only."
        ),
        "strengths": ["The exported evidence is traceable by stable evidence id."],
        "weaknesses_gaps": ["A human operator must decide commercial relevance."],
        "opportunity_assessment": (
            "Synthetic acceptance opportunity; no real business claim is made."
        ),
        "confidence": "high",
        "uncertainty": ["No traffic, conversion or revenue impact is inferred."],
        "recommended_next_action": "Request human review of the cited finding.",
        "suggested_messaging_positioning": [
            "Use only the directly observed issue if messaging is later approved."
        ],
        "evidence_refs": [refs[0]],
        "safe_actions": [
            {
                "action": "request_human_review",
                "reason": (
                    "Operator acceptance keeps execution explicitly human-controlled."
                ),
                "evidence_refs": [refs[0]],
            }
        ],
    }
    result["result_hash_sha256"] = result_integrity_hash(result)

    page.get_by_role("link", name="Import reviewed result").click()
    page.wait_for_url("**/ai-review/import")
    page.get_by_label("Reviewed result JSON").fill(json.dumps(result))
    page.get_by_role("button", name="Validate and import").click()
    page.wait_for_url("**/ai-review?imported=true")
    acceptance._assert_text(page, "Reviewed result imported")
    page.get_by_role("link", name="review-e2e-standard-exchange").click()
    page.wait_for_url("**/ai-review/results/review-e2e-standard-exchange")
    acceptance._assert_text(
        page,
        "AI interpretation — imported reasoning, not VERIDRA observation",
    )
    acceptance._assert_text(page, "request_human_review")

    page.goto(monitoring_url, wait_until="networkidle")
    return monitoring_url


def _assert_change_request_page(page: Page) -> None:
    """Wait for navigation and prove the browser reached the Change Request route."""
    page.wait_for_load_state("networkidle")
    if "/deal/change-requests" not in page.url:
        raise AssertionError(
            "Change Request navigation did not reach the expected route: "
            f"{page.url!r}"
        )


def _delivery_closure(page: Page, project_url: str) -> None:
    """Prove revision, customer review, scope-change, handoff and closure in Chromium."""
    page.goto(project_url, wait_until="networkidle")
    page.get_by_role("link", name="Delivery & closure").click()
    page.wait_for_url("**/delivery")
    delivery_url = page.url
    acceptance._assert_text(page, "Delivery setup")

    page.locator("textarea[name='deliverables']").fill(
        "Client report\nImplemented fixes\nVerification summary"
    )
    page.locator("input[name='revision_policy']").fill(
        "One included revision against agreed scope; additional work requires an "
        "approved Change Request."
    )
    page.locator("input[name='included_revisions']").fill("1")
    page.locator("textarea[name='acceptance_criteria']").fill(
        "Agreed deliverables are complete, verified and accepted by the customer."
    )
    page.locator("input[name='final_balance_required']").check()
    page.get_by_role("button", name="Save delivery setup").click()
    page.wait_for_url(delivery_url)
    page.get_by_role("button", name="Mark deliverables complete & request review").click()
    page.wait_for_url(delivery_url)
    acceptance._assert_text(page, "Awaiting Review")

    page.locator(
        "form[action$='/changes-requested'] textarea[name='reference']"
    ).fill("Customer email requests one in-scope copy revision.")
    page.get_by_role("button", name="Record changes requested").click()
    page.wait_for_url(delivery_url)
    acceptance._assert_text(page, "Revision In Progress")
    page.locator(
        "form[action$='/revision-completed'] textarea[name='reference']"
    ).fill("Revision 1 completed and verification rerun.")
    page.get_by_role("button", name="Complete revision & return to review").click()
    page.wait_for_url(delivery_url)

    page.locator(
        "form[action$='/unresponsive'] input[name='reference']"
    ).fill("Synthetic follow-up after review deadline; no customer reply.")
    page.get_by_role("button", name="Mark unresponsive").click()
    page.wait_for_url(delivery_url)
    acceptance._assert_text(page, "project remains open")
    page.get_by_role("button", name="Resume customer review").click()
    page.wait_for_url(delivery_url)

    page.get_by_role("link", name="Out-of-scope change request").click()
    _assert_change_request_page(page)
    acceptance._assert_text(page, "Scope changes")
    page.locator("textarea[name='summary']").fill(
        "Add a new landing page outside the accepted delivery scope."
    )
    page.locator("input[name='requested_by']").fill("customer")
    page.locator("textarea[name='scope_impact']").fill(
        "Additional page design, implementation and verification."
    )
    page.locator("input[name='price_impact']").fill("Additional fixed fee required.")
    page.locator("input[name='timeline_impact']").fill(
        "Adds two working days after approval."
    )
    page.get_by_role("button", name="Record change request").click()
    _assert_change_request_page(page)
    change_status_form = page.locator("form[action$='/status']")
    change_status_form.locator("select[name='status']").select_option("approved")
    change_status_form.locator("input[name='decision_reference']").fill(
        "Synthetic customer approval for out-of-scope change and price impact."
    )
    page.get_by_role("button", name="Update change request").click()
    _assert_change_request_page(page)
    acceptance._assert_text(page, "approved")
    change_status_form = page.locator("form[action$='/status']")
    change_status_form.locator("select[name='status']").select_option("incorporated")
    change_status_form.locator("input[name='resulting_proposal_version']").fill("2")
    page.get_by_role("button", name="Update change request").click()
    _assert_change_request_page(page)
    acceptance._assert_text(page, "incorporated")

    page.goto(delivery_url, wait_until="networkidle")
    page.locator("form[action$='/accept'] textarea[name='reference']").fill(
        "Synthetic customer acceptance after included revision and approved scope decision."
    )
    page.get_by_role("button", name="Record customer acceptance").click()
    page.wait_for_url(delivery_url)
    acceptance._assert_text(page, "Customer accepted")
    page.get_by_role("button", name="Start handoff").click()
    page.wait_for_url(delivery_url)

    handoff_form = page.locator("form[action$='/handoff-complete']")
    handoff_form.locator("input[name='backups']").check()
    handoff_form.locator("input[name='access']").check()
    handoff_form.locator("input[name='documentation']").check()
    handoff_form.locator("textarea[name='reference']").fill(
        "Synthetic backup, access transfer and handoff-guide acknowledgement."
    )
    page.get_by_role("button", name="Complete handoff").click()
    page.wait_for_url(delivery_url)
    acceptance._assert_text(page, "Final completion gate")

    page.locator("textarea[name='completion_summary']").fill(
        "Synthetic delivery completed, revised, accepted, handed off and financially closed."
    )
    page.locator("input[name='final_balance_evidence']").fill(
        "Synthetic invoice balance marked paid: INV-E2E-FINAL-001."
    )
    page.locator("select[name='recurring_decision']").select_option("declined")
    page.get_by_role("button", name="Close project").click()
    page.wait_for_url(delivery_url)
    acceptance._assert_text(page, "Project closed")
    acceptance._assert_text(page, "Recurring service: Declined")


def _report(page: Page, project_url: str, evidence: Path) -> None:
    """Exercise the real PDF control and verify the actual browser-downloaded artifact."""
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

    with page.expect_download(timeout=90_000) as download_info:
        page.get_by_role("link", name="Download PDF").click()
    download = download_info.value
    pdf = evidence / "VERIDRA_E2E_REPORT.pdf"
    download.save_as(pdf)
    content = pdf.read_bytes()
    if not content.startswith(b"%PDF-") or len(content) < 1000:
        raise AssertionError("Downloaded branded report is not a valid non-empty PDF.")

    page.get_by_role("link", name="Email PDF report").click()
    page.get_by_label("Recipient").fill("acceptance@example.com")
    page.get_by_label("Subject").fill("VERIDRA E2E report delivery")
    page.get_by_label("Message").fill("Synthetic local capture only.")
    page.get_by_role("button", name="Send PDF report").click(timeout=90_000)
    page.wait_for_load_state("load", timeout=90_000)
    if not page.url.endswith("?delivery=delivered"):
        visible = page.locator("body").inner_text(timeout=10_000)[:2000]
        raise AssertionError(
            "Report delivery did not reach delivered state. "
            f"url={page.url!r}; visible={visible!r}"
        )
    acceptance._assert_text(page, "SMTP accepted the report delivery")
    _delivery_closure(page, project_url)


def _wait_autonomous_monitoring(
    runtime_log: Path,
    page: Page,
    monitoring_url: str,
) -> None:
    """Run the established monitor wait, then prove Progress/Changes in Chromium."""
    _ORIGINAL_WAIT_AUTONOMOUS_MONITORING(runtime_log, page, monitoring_url)
    project_url = monitoring_url.rsplit("/monitoring", 1)[0]
    page.goto(project_url, wait_until="networkidle")
    progress_link = page.get_by_role("link", name="Progress / Changes")
    progress_link.wait_for(state="visible", timeout=10_000)
    progress_link.click()
    page.wait_for_url("**/progress")
    page.wait_for_load_state("networkidle")
    acceptance._assert_text(page, "Progress / Changes")
    acceptance._assert_text(page, "Change details")
    acceptance._assert_text(page, "Pages changed")
    acceptance._assert_text(page, "New findings")
    acceptance._assert_text(page, "Resolved findings")
    acceptance._assert_text(page, "Persistent findings")


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


_ORIGINAL_COMPLETE_ONBOARDING = acceptance._complete_onboarding
_ORIGINAL_MANUAL_ASSESSMENT = acceptance._manual_assessment
_ORIGINAL_WAIT_AUTONOMOUS_MONITORING = acceptance._wait_autonomous_monitoring
acceptance._run_launcher = _run_launcher
acceptance._create_and_qualify_prospect = _create_and_qualify_prospect
acceptance._complete_onboarding = _complete_onboarding_with_booking_gate
acceptance._manual_assessment = _manual_assessment
acceptance._report = _report
acceptance._wait_autonomous_monitoring = _wait_autonomous_monitoring


if __name__ == "__main__":
    _preserve_playwright_browser_cache()
    acceptance.main()