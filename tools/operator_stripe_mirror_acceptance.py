from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import sys
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE_URL = "http://127.0.0.1:8010"
BUSINESS = "Webify Test Customer"
TARGET = "https://example.com/"
INVOICE_NUMBER = "A7F357F0-0001"
STRIPE_INVOICE_ID = "in_1UJy58P00ovZDLvDoKnY6lzd"
PAYMENT_ID = "pi_3UJy58P00ovZDLvD1bVWIFQb"
SUBSCRIPTION_ID = "sub_1UJy58P00ovZDLvDtRgVMAw7"
NEXT_BILLING = "2026-10-26"
STATE_ROOT = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "Veridra"
STATE_DIR = STATE_ROOT / "provider-acceptance"
STATE_FILE = STATE_DIR / "stripe-mirror.json"


def _prompt(name: str, *, secret: bool = False) -> str:
    value = getpass.getpass(f"{name}: ") if secret else input(f"{name}: ")
    value = value.strip()
    if not value:
        raise SystemExit(f"{name} is required.")
    return value


def _credentials() -> tuple[str, str, str]:
    print("[Stripe mirror] Enter VERIDRA login locally. Credentials are not written to evidence.")
    workspace = _prompt("Workspace slug")
    email = _prompt("VERIDRA email")
    password = _prompt("VERIDRA password", secret=True)
    return workspace, email, password


def _capture(page: Page, evidence: Path, name: str, report: dict[str, object]) -> None:
    png = evidence / f"{name}.png"
    txt = evidence / f"{name}.txt"
    page.screenshot(path=str(png), full_page=True)
    txt.write_text(page.locator("body").inner_text(), encoding="utf-8")
    report.setdefault("steps", []).append(
        {"name": name, "url": page.url, "title": page.title(), "screenshot": png.name, "text": txt.name}
    )


def _login(page: Page, workspace: str, email: str, password: str) -> None:
    page.goto(f"{BASE_URL}/login", wait_until="networkidle")
    page.get_by_label("Workspace slug").fill(workspace)
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password").fill(password)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url(f"{BASE_URL}/agency", timeout=20_000)


def _create_prospect(page: Page) -> str:
    # Reuse the deterministic synthetic prospect if a prior interrupted run already created it.
    page.goto(f"{BASE_URL}/agency/prospects", wait_until="networkidle")
    row = page.locator("tr").filter(has_text=BUSINESS)
    if row.count() >= 1:
        row.last.get_by_role("link", name="Review").click()
        page.wait_for_url("**/agency/prospects/*")
        prospect_url = page.url
    else:
        page.goto(f"{BASE_URL}/agency/prospects/new", wait_until="networkidle")
        page.get_by_label("Business name").fill(BUSINESS)
        page.get_by_label("Website").fill(TARGET)
        page.get_by_label("Sector").fill("Synthetic Stripe sandbox customer")
        page.get_by_label("Locality").fill("Dublin")
        page.get_by_label("Administrative area").fill("Dublin")
        page.get_by_label("Country code").fill("IE")
        page.get_by_label("Contact email").fill("ralbas.int@gmail.com")
        page.get_by_label("Evidence / discovery note").fill(
            "Synthetic Stripe sandbox customer for #296 provider acceptance. No real outreach."
        )
        page.get_by_role("button", name="Create prospect").click()
        page.wait_for_url("**/agency/prospects/*")
        prospect_url = page.url

    disclosure = page.locator("details.disclosure").filter(has_text="Qualification score")
    disclosure.evaluate("element => element.setAttribute('open', '')")
    for name in (
        "active_real_business",
        "website_commercial_importance",
        "business_economic_value",
        "business_size_fit",
        "decision_maker_reachability",
        "website_manageability",
        "no_existing_web_team",
    ):
        page.locator(f"select[name='{name}']").select_option("2", force=True)
    page.locator("textarea[name='reason']").fill(
        "Synthetic provider-acceptance fixture intentionally qualifies for the supported workflow."
    )
    page.get_by_role("button", name="Save qualification").click()
    page.wait_for_url(prospect_url)
    page.get_by_text("14/14", exact=False).first.wait_for(state="visible")
    return prospect_url


def _create_customer_from_supported_sales_flow(page: Page, prospect_url: str) -> str:
    deal_url = f"{prospect_url}/deal"
    page.goto(deal_url, wait_until="networkidle")

    page.locator("select[name='reply_outcome']").select_option("positive")
    page.locator("textarea[name='conversation_summary']").fill(
        "Synthetic acceptance of the documented Stripe sandbox scenario."
    )
    page.locator("input[name='next_action']").fill("Complete synthetic discovery and proposal.")
    page.get_by_role("button", name="Save reply context").click()
    page.wait_for_url(deal_url)

    discovery = page.locator("form[action$='/deal/discovery']")
    values = {
        "goals": "Validate the Webify Presence Care provider/payment operating boundary.",
        "current_platform": "Synthetic",
        "hosting": "Synthetic",
        "decision_maker": "Webify operator",
        "urgency": "M3 provider acceptance",
        "constraints": "No real customer and no real outreach.",
        "access_readiness": "Synthetic public target only.",
        "measurable_scope": "Exercise provider references through the supported VERIDRA workflow.",
        "deliverables": "Persistent provider mirror, recurring billing state and acceptance evidence.",
        "exclusions": "Real customer work, production pricing and live-card processing.",
        "assumptions": "Stripe sandbox remains the authoritative payment source.",
        "timeline": "Provider acceptance exercise only",
    }
    for name, value in values.items():
        discovery.locator(f"[name='{name}']").fill(value)
    discovery.get_by_role("button", name="Save discovery").click()
    page.wait_for_url(deal_url)

    qualification = page.locator("form[action$='/deal/recurring-qualification']")
    qualification.locator("select[name='recurring_qualification']").select_option("presence_care")
    qualification.locator("textarea[name='recurring_qualification_evidence']").fill(
        "Synthetic M3 sandbox scenario explicitly exercises recurring Presence Care at EUR 99/month."
    )
    qualification.get_by_role("button", name="Save offer qualification").click()
    page.wait_for_url(deal_url)

    proposal = page.locator("form[action$='/deal/proposals']")
    proposal.locator("input[name='title']").fill("Webify Presence Care Activation — M3 Sandbox")
    proposal.locator("textarea[name='scope']").last.fill(
        "Synthetic activation plus recurring Presence Care provider acceptance."
    )
    proposal.locator("textarea[name='deliverables']").last.fill(
        "Stripe sandbox billing evidence mirrored into VERIDRA."
    )
    proposal.locator("textarea[name='exclusions']").last.fill("No real customer work.")
    proposal.locator("textarea[name='assumptions']").last.fill(
        "Stripe sandbox evidence is authoritative for this synthetic run."
    )
    proposal.locator("input[name='timeline']").last.fill("Synthetic acceptance only")
    proposal.locator("input[name='valid_until']").fill(
        (datetime.now(UTC).date() + timedelta(days=14)).isoformat()
    )
    proposal.locator("input[name='price_amount']").fill("149.00")
    proposal.locator("input[name='currency']").fill("EUR")
    proposal.locator("input[name='recurring_amount']").fill("99.00")
    proposal.locator("input[name='recurring_cadence']").fill("monthly")
    before = page.locator("div.proposal").count()
    proposal.get_by_role("button", name="Create proposal version").click()
    page.wait_for_url(deal_url)
    version = page.locator("div.proposal").count()
    if version != before + 1:
        raise AssertionError("Proposal was not created through the supported UI.")

    status = page.locator(f"form[action$='/deal/proposals/{version}/status']")
    status.locator("select[name='status']").select_option("sent")
    status.get_by_role("button", name="Update proposal status").click()
    page.wait_for_url(deal_url)

    status = page.locator(f"form[action$='/deal/proposals/{version}/status']")
    status.locator("select[name='status']").select_option("accepted")
    status.locator("input[name='acceptance_reference']").fill(
        f"Synthetic M3 acceptance; Stripe sandbox subscription {SUBSCRIPTION_ID}."
    )
    status.get_by_role("button", name="Update proposal status").click()
    page.wait_for_url(deal_url)

    page.goto(f"{BASE_URL}/agency/customers", wait_until="networkidle")
    cards = page.locator("article.card").filter(has_text=BUSINESS)
    if cards.count() < 1:
        raise AssertionError("Accepted proposal did not create the synthetic customer.")
    cards.last.get_by_role("link", name="Open customer").click()
    page.wait_for_url("**/agency/customers/*")
    return page.url


def _open_work_gate_and_create_project(page: Page, customer_url: str) -> str:
    page.goto(customer_url, wait_until="networkidle")

    page.get_by_label("Terms / agreement reference").fill("WEBIFY-M3-SYNTHETIC-TERMS")
    page.get_by_label("Terms version").fill("2026-09")
    page.get_by_label("Accepted at").fill("2026-09-26T16:04")
    page.get_by_label("External signature reference").fill("SYNTHETIC-NO-REAL-SIGNATURE")
    page.get_by_label("Acceptance evidence").fill(
        f"Synthetic provider-acceptance record bound to Stripe subscription {SUBSCRIPTION_ID}."
    )

    page.get_by_label("Billing status").select_option("paid")
    page.get_by_label("External invoice reference").fill(INVOICE_NUMBER)
    page.get_by_label("Invoice amount").fill("248.00")
    page.get_by_label("Currency").fill("EUR")
    page.get_by_label("Issued on").fill("2026-09-26")
    page.get_by_label("Due on").fill("2026-09-26")
    deposit = page.get_by_label("Deposit / upfront payment required before work")
    if not deposit.is_checked():
        deposit.check()
    page.get_by_label("Required upfront amount").fill("149.00")
    page.get_by_label("Amount paid").fill("248.00")
    page.get_by_label("Payment evidence reference").fill(PAYMENT_ID)
    page.get_by_label("Paid at").fill("2026-09-26T16:04")
    page.get_by_label("Payment method reference").fill("Stripe sandbox Visa ****4242")
    page.get_by_label("Provider transaction reference").fill(PAYMENT_ID)
    page.get_by_label("Billing note").fill(
        f"Stripe sandbox invoice object {STRIPE_INVOICE_ID}; subscription {SUBSCRIPTION_ID}; "
        "EUR 149 activation + EUR 99 first month."
    )

    for label in (
        "Primary contact confirmed",
        "Service scope confirmed",
        "Commercial terms confirmed",
        "Access/domain/hosting requirements confirmed",
        "Kickoff completed",
    ):
        checkbox = page.get_by_label(label)
        if not checkbox.is_checked():
            checkbox.check()
    page.get_by_label("Customer status").select_option("active")
    page.get_by_label("Commercial / onboarding notes").fill(
        "Synthetic persistent M3 provider-acceptance customer. No real outreach/customer."
    )
    page.get_by_role("button", name="Save customer").click()
    page.wait_for_url(customer_url)
    page.get_by_text("Work may start", exact=False).first.wait_for(state="visible")

    page.get_by_label("Project name").fill("Webify Test Customer — Presence Care M3")
    page.get_by_label("Delivery target URL").fill(TARGET)
    page.get_by_role("button", name="Create and link project").click()
    page.wait_for_url(customer_url)

    page.get_by_role("link", name="Webify Test Customer — Presence Care M3").click()
    page.wait_for_url("**/agency/projects/*")
    return page.url


def _activate_and_mirror_paid(page: Page, project_url: str) -> str:
    recurring_url = f"{project_url}/recurring"
    page.goto(recurring_url, wait_until="networkidle")

    page.locator("textarea[name='scope']").fill("Monthly website health review\nMonitoring review")
    page.locator("textarea[name='deliverables']").fill(
        "Monthly monitoring review\nMonthly customer summary"
    )
    page.locator("textarea[name='exclusions']").fill("New builds\nThird-party fees")
    page.locator("input[name='fee']").fill("99.00")
    page.locator("input[name='currency']").fill("EUR")
    page.locator("select[name='billing_cadence']").select_option("monthly")
    page.locator("input[name='cadence_description']").fill("Monthly Presence Care")
    page.locator("input[name='response_time']").fill("Review within two business days")
    page.locator("input[name='escalation_expectations']").fill(
        "Payment/provider exceptions block recurring delivery until reconciled."
    )
    page.locator("input[name='effective_from']").fill("2026-09-26")
    page.get_by_role("button", name="Save recurring plan").click()
    page.wait_for_url(recurring_url)

    page.get_by_role("button", name="Mark plan offered").click()
    page.wait_for_url(recurring_url)

    page.locator("textarea[name='acceptance_reference']").fill(
        f"Stripe sandbox subscription {SUBSCRIPTION_ID}; synthetic M3 acceptance."
    )
    page.locator("input[name='start_date']").fill("2026-09-26")
    page.locator("input[name='next_billing_date']").fill(NEXT_BILLING)
    page.locator("input[name='renewal_date']").fill("2026-12-25")
    page.locator("input[name='minimum_term_months']").fill("0")
    page.locator("select[name='renewal_behavior']").select_option("fixed_term")
    page.locator("input[name='monitoring_cadence']").fill("Monthly")
    page.locator("input[name='report_cadence']").fill("Monthly")
    page.get_by_role("button", name="Record acceptance & activate").click()
    page.wait_for_url(recurring_url)

    billing = page.locator("form[action$='/payment']")
    billing.locator("input[name='invoice_reference']").fill(INVOICE_NUMBER)
    billing.locator("select[name='payment_state']").select_option("paid")
    billing.locator("input[name='payment_reference']").fill(PAYMENT_ID)
    billing.locator("input[name='next_billing_date']").fill(NEXT_BILLING)
    billing.get_by_role("button", name="Record billing state").click()
    page.wait_for_url(recurring_url)
    page.get_by_text("Active", exact=False).first.wait_for(state="visible")
    history = page.locator("details").filter(has_text="Recurring lifecycle history")
    history.evaluate("element => element.setAttribute('open', '')")
    page.get_by_text(INVOICE_NUMBER, exact=False).first.wait_for(state="visible")
    page.get_by_text(PAYMENT_ID, exact=False).first.wait_for(state="visible")
    return recurring_url


def _load_state() -> dict[str, str]:
    if not STATE_FILE.exists():
        raise SystemExit(
            f"Provider mirror state was not found at {STATE_FILE}. Run phase 'paid' first."
        )
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def _record_payment_phase(page: Page, recurring_url: str, phase: str) -> None:
    page.goto(recurring_url, wait_until="networkidle")
    invoice = _prompt(f"{phase.capitalize()} Stripe invoice reference")
    payment = _prompt(f"{phase.capitalize()} Stripe payment/provider reference")
    next_billing = input("Next billing date YYYY-MM-DD (leave blank to keep current): ").strip()

    billing = page.locator("form[action$='/payment']")
    billing.locator("input[name='invoice_reference']").fill(invoice)
    billing.locator("select[name='payment_state']").select_option(
        "failed" if phase == "failed" else "paid"
    )
    billing.locator("input[name='payment_reference']").fill(payment)
    if next_billing:
        billing.locator("input[name='next_billing_date']").fill(next_billing)
    billing.get_by_role("button", name="Record billing state").click()
    page.wait_for_url(recurring_url)
    expected = "Payment Blocked" if phase == "failed" else "Active"
    page.get_by_text(expected, exact=False).first.wait_for(state="visible")
    history = page.locator("details").filter(has_text="Recurring lifecycle history")
    history.evaluate("element => element.setAttribute('open', '')")
    page.get_by_text(invoice, exact=False).first.wait_for(state="visible")
    page.get_by_text(payment, exact=False).first.wait_for(state="visible")


def _cancel_pending_phase(page: Page, recurring_url: str) -> None:
    page.goto(recurring_url, wait_until="networkidle")
    notice_date = _prompt("Stripe cancellation notice date YYYY-MM-DD")
    effective_date = _prompt("Stripe effective cancellation date YYYY-MM-DD")
    reference = _prompt("Stripe cancellation/subscription reference")

    cancel = page.locator("form[action$='/cancel-notice']")
    cancel.locator("input[name='notice_date']").fill(notice_date)
    cancel.locator("input[name='effective_date']").fill(effective_date)
    cancel.locator("textarea[name='reference']").fill(reference)
    cancel.get_by_role("button", name="Record cancellation notice").click()
    page.wait_for_url(recurring_url)
    page.get_by_text("Cancellation Pending", exact=False).first.wait_for(state="visible")
    history = page.locator("details").filter(has_text="Recurring lifecycle history")
    history.evaluate("element => element.setAttribute('open', '')")
    page.get_by_text(reference, exact=False).first.wait_for(state="visible")


def _cancelled_phase(page: Page, recurring_url: str) -> None:
    page.goto(recurring_url, wait_until="networkidle")
    effective_date = _prompt("Stripe effective cancellation date YYYY-MM-DD")
    reference = _prompt("Stripe cancellation/subscription reference")
    page.locator("input[name='effective_date']").fill(effective_date)
    page.locator("textarea[name='exit_handoff_reference']").fill(
        f"Synthetic M3 provider acceptance cancellation; Stripe reference {reference}."
    )
    page.get_by_role("button", name="Complete cancellation").click()
    page.wait_for_url(recurring_url)
    page.get_by_text("Recurring service is cancelled", exact=False).wait_for(state="visible")
    history = page.locator("details").filter(has_text="Recurring lifecycle history")
    history.evaluate("element => element.setAttribute('open', '')")
    page.get_by_text(reference, exact=False).first.wait_for(state="visible")


def run(phase: str) -> Path:
    workspace, email, password = _credentials()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    evidence = Path.home() / "Downloads" / f"VERIDRA_STRIPE_MIRROR_{phase.upper()}_{stamp}"
    evidence.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {
        "contract": "veridra_stripe_provider_mirror_acceptance",
        "phase": phase,
        "started_at": datetime.now(UTC).isoformat(),
        "passed": False,
        "steps": [],
    }

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()
            page.set_default_timeout(20_000)
            page.set_default_navigation_timeout(30_000)

            _login(page, workspace, email, password)
            _capture(page, evidence, "01-authenticated", report)

            if phase == "paid":
                prospect_url = _create_prospect(page)
                _capture(page, evidence, "02-qualified-synthetic-prospect", report)
                customer_url = _create_customer_from_supported_sales_flow(page, prospect_url)
                _capture(page, evidence, "03-customer-created-from-accepted-proposal", report)
                project_url = _open_work_gate_and_create_project(page, customer_url)
                _capture(page, evidence, "04-paid-customer-linked-project", report)
                recurring_url = _activate_and_mirror_paid(page, project_url)
                _capture(page, evidence, "05-stripe-paid-mirror-active", report)

                STATE_DIR.mkdir(parents=True, exist_ok=True)
                STATE_FILE.write_text(
                    json.dumps(
                        {
                            "business": BUSINESS,
                            "customer_url": customer_url,
                            "project_url": project_url,
                            "recurring_url": recurring_url,
                            "invoice_number": INVOICE_NUMBER,
                            "stripe_invoice_id": STRIPE_INVOICE_ID,
                            "payment_id": PAYMENT_ID,
                            "subscription_id": SUBSCRIPTION_ID,
                            "next_billing_date": NEXT_BILLING,
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            else:
                state = _load_state()
                recurring_url = state["recurring_url"]
                if phase in {"failed", "recovered"}:
                    _record_payment_phase(page, recurring_url, phase)
                elif phase == "cancel-pending":
                    _cancel_pending_phase(page, recurring_url)
                elif phase == "cancelled":
                    _cancelled_phase(page, recurring_url)
                _capture(page, evidence, f"02-{phase}-mirror", report)

            page.goto(f"{BASE_URL}/agency/recurring-services", wait_until="networkidle")
            _capture(page, evidence, f"99-recurring-revenue-after-{phase}", report)
            context.close()
            browser.close()

        report["passed"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        report["finished_at"] = datetime.now(UTC).isoformat()
        (evidence / "report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        archive = evidence.with_suffix(".zip")
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(evidence.iterdir()):
                zf.write(path, arcname=path.name)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"Evidence ZIP: {archive}")

    return archive


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase",
        choices=("paid", "failed", "recovered", "cancel-pending", "cancelled"),
        default="paid",
    )
    args = parser.parse_args()
    run(args.phase)


if __name__ == "__main__":
    main()
