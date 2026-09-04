from __future__ import annotations

import operator_e2e_acceptance as acceptance
import operator_e2e_acceptance_entry as hardened
import operator_visual_acceptance_entry as visual
from playwright.sync_api import Page


def _assert_delivery_url(page: Page, delivery_url: str) -> None:
    page.wait_for_load_state("networkidle")
    if page.url != delivery_url:
        raise AssertionError(f"Delivery transition left expected route: {page.url!r}")


def _delivery_closure_with_recurring(page: Page, project_url: str) -> None:
    """Complete sprint delivery, then exercise the recurring lifecycle in Chromium."""
    page.goto(f"{project_url}/delivery", wait_until="networkidle")
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
    _assert_delivery_url(page, delivery_url)
    page.get_by_role("button", name="Mark deliverables complete & request review").click()
    _assert_delivery_url(page, delivery_url)

    page.locator(
        "form[action$='/changes-requested'] textarea[name='reference']"
    ).fill("Customer email requests one in-scope copy revision.")
    page.get_by_role("button", name="Record changes requested").click()
    _assert_delivery_url(page, delivery_url)
    page.locator(
        "form[action$='/revision-completed'] textarea[name='reference']"
    ).fill("Revision 1 completed and verification rerun.")
    page.get_by_role("button", name="Complete revision & return to review").click()
    _assert_delivery_url(page, delivery_url)

    page.locator("form[action$='/unresponsive'] input[name='reference']").fill(
        "Synthetic follow-up after review deadline; no customer reply."
    )
    page.get_by_role("button", name="Mark unresponsive").click()
    _assert_delivery_url(page, delivery_url)
    acceptance._assert_text(page, "project remains open")
    page.get_by_role("button", name="Resume customer review").click()
    _assert_delivery_url(page, delivery_url)

    page.get_by_role("link", name="Out-of-scope change request").click()
    hardened._assert_change_request_page(page)
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
    hardened._assert_change_request_page(page)
    change_form = page.locator("form[action$='/status']")
    change_form.locator("select[name='status']").select_option("approved")
    change_form.locator("input[name='decision_reference']").fill(
        "Synthetic customer approval for out-of-scope work and price impact."
    )
    page.get_by_role("button", name="Update change request").click()
    hardened._assert_change_request_page(page)
    acceptance._assert_text(page, "approved")

    page.goto(delivery_url, wait_until="networkidle")
    page.locator("form[action$='/accept'] textarea[name='reference']").fill(
        "Synthetic customer acceptance after revision and scope decision."
    )
    page.get_by_role("button", name="Record customer acceptance").click()
    _assert_delivery_url(page, delivery_url)
    page.get_by_role("button", name="Start handoff").click()
    _assert_delivery_url(page, delivery_url)

    handoff = page.locator("form[action$='/handoff-complete']")
    handoff.locator("input[name='backups']").check()
    handoff.locator("input[name='access']").check()
    handoff.locator("input[name='documentation']").check()
    handoff.locator("textarea[name='reference']").fill(
        "Synthetic backup, access-transfer and documentation handoff evidence."
    )
    page.get_by_role("button", name="Complete handoff").click()
    _assert_delivery_url(page, delivery_url)

    page.locator("textarea[name='completion_summary']").fill(
        "Synthetic sprint delivered, accepted, handed off and financially closed."
    )
    page.locator("input[name='final_balance_evidence']").fill(
        "Synthetic final invoice balance paid: INV-E2E-FINAL-001."
    )
    page.locator("select[name='recurring_decision']").select_option("accepted")
    page.get_by_role("button", name="Close project").click()
    _assert_delivery_url(page, delivery_url)
    acceptance._assert_text(page, "Project closed")
    acceptance._assert_text(page, "Recurring service: Accepted")
    visual._capture(page, "17-delivery-closed-recurring-accepted")

    _recurring_lifecycle(page, project_url)


def _recurring_lifecycle(page: Page, project_url: str) -> None:
    recurring_url = f"{project_url}/recurring"
    page.goto(recurring_url, wait_until="networkidle")
    acceptance._assert_text(page, "Configure recurring plan")
    visual._capture(page, "18-recurring-draft")

    page.locator("textarea[name='scope']").fill(
        "Monthly website health review\nMonitoring review"
    )
    page.locator("textarea[name='deliverables']").fill(
        "Monthly monitoring review\nMonthly client summary"
    )
    page.locator("textarea[name='exclusions']").fill(
        "New page builds\nThird-party paid media"
    )
    page.locator("input[name='fee']").fill("99.00")
    page.locator("input[name='currency']").fill("EUR")
    page.locator("select[name='billing_cadence']").select_option("monthly")
    page.locator("input[name='cadence_description']").fill("Monthly review and report")
    page.locator("input[name='response_time']").fill("Review within two business days")
    page.locator("input[name='escalation_expectations']").fill(
        "Critical availability evidence surfaced first"
    )
    page.locator("input[name='effective_from']").fill("2026-09-05")
    page.get_by_role("button", name="Save recurring plan").click()
    page.wait_for_url(recurring_url)
    page.get_by_role("button", name="Mark plan offered").click()
    page.wait_for_url(recurring_url)
    acceptance._assert_text(page, "Offered")

    page.locator("textarea[name='acceptance_reference']").fill(
        "Synthetic customer accepts recurring plan v1."
    )
    page.locator("input[name='start_date']").fill("2026-09-05")
    page.locator("input[name='next_billing_date']").fill("2026-10-05")
    page.locator("input[name='renewal_date']").fill("2026-10-05")
    page.locator("input[name='minimum_term_months']").fill("0")
    page.locator("select[name='renewal_behavior']").select_option("manual")
    page.locator("input[name='monitoring_cadence']").fill("Monthly")
    page.locator("input[name='report_cadence']").fill("Monthly")
    page.get_by_role("button", name="Record acceptance & activate").click()
    page.wait_for_url(recurring_url)
    acceptance._assert_text(page, "Active")
    visual._capture(page, "19-recurring-active")

    deliverable_form = page.locator("form[action$='/deliverable']")
    deliverable_form.locator("input[name='deliverable']").fill(
        "Monthly monitoring review"
    )
    deliverable_form.locator("input[name='reference']").fill(
        "Synthetic recurring monitoring/report evidence."
    )
    page.get_by_role("button", name="Record deliverable").click()
    page.wait_for_url(recurring_url)

    page.locator("form[action$='/pause'] textarea[name='reference']").fill(
        "Synthetic customer-requested pause."
    )
    page.get_by_role("button", name="Pause").click()
    page.wait_for_url(recurring_url)
    acceptance._assert_text(page, "Paused")
    page.locator("form[action$='/resume'] textarea[name='reference']").fill(
        "Synthetic customer requests resume."
    )
    page.get_by_role("button", name="Resume service").click()
    page.wait_for_url(recurring_url)

    billing = page.locator("form[action$='/payment']")
    billing.locator("input[name='invoice_reference']").fill("INV-RECUR-E2E-002")
    billing.locator("select[name='payment_state']").select_option("failed")
    billing.locator("input[name='payment_reference']").fill("FAILED-E2E-002")
    billing.locator("input[name='next_billing_date']").fill("2026-10-05")
    page.get_by_role("button", name="Record billing state").click()
    page.wait_for_url(recurring_url)
    acceptance._assert_text(page, "Payment Blocked")
    visual._capture(page, "20-recurring-payment-blocked")

    billing = page.locator("form[action$='/payment']")
    billing.locator("input[name='invoice_reference']").fill("INV-RECUR-E2E-002")
    billing.locator("select[name='payment_state']").select_option("paid")
    billing.locator("input[name='payment_reference']").fill("PAY-RECUR-E2E-002")
    billing.locator("input[name='next_billing_date']").fill("2026-11-05")
    page.get_by_role("button", name="Record billing state").click()
    page.wait_for_url(recurring_url)
    acceptance._assert_text(page, "Active")

    renew = page.locator("form[action$='/renew']")
    renew.locator("textarea[name='scope']").fill(
        "Monthly website health review\nMonitoring review\nQuarterly conversion-path review"
    )
    renew.locator("textarea[name='deliverables']").fill(
        "Monthly monitoring review\nMonthly client summary"
    )
    renew.locator("textarea[name='exclusions']").fill(
        "New page builds\nThird-party paid media"
    )
    renew.locator("input[name='fee']").fill("129.00")
    renew.locator("input[name='currency']").fill("EUR")
    renew.locator("select[name='billing_cadence']").select_option("monthly")
    renew.locator("input[name='cadence_description']").fill(
        "Monthly review plus quarterly conversion-path review"
    )
    renew.locator("input[name='effective_from']").fill("2026-10-05")
    renew.locator("textarea[name='renewal_reference']").fill(
        "Synthetic customer approval for recurring plan v2 and new fee."
    )
    page.get_by_role("button", name="Create new plan version").click()
    page.wait_for_url(recurring_url)
    acceptance._assert_text(page, "129.00 EUR")
    acceptance._assert_text(page, "Version: 2")
    visual._capture(page, "21-recurring-renewed")

    cancel = page.locator("form[action$='/cancel-notice']")
    cancel.locator("input[name='notice_date']").fill("2026-10-20")
    cancel.locator("input[name='effective_date']").fill("2026-11-05")
    cancel.locator("textarea[name='reference']").fill("Synthetic cancellation notice.")
    page.get_by_role("button", name="Record cancellation notice").click()
    page.wait_for_url(recurring_url)
    acceptance._assert_text(page, "Cancellation Pending")

    page.locator("input[name='effective_date']").fill("2026-11-05")
    page.locator("textarea[name='exit_handoff_reference']").fill(
        "Synthetic recurring exit and ownership/access handoff evidence."
    )
    page.get_by_role("button", name="Complete cancellation").click()
    page.wait_for_url(recurring_url)
    acceptance._assert_text(page, "Recurring service is cancelled")
    visual._capture(page, "22-recurring-cancelled")

    page.goto(page.url.split("/projects/", 1)[0] + "/recurring-services", wait_until="networkidle")
    acceptance._assert_text(page, "Recurring revenue")
    acceptance._assert_text(page, "Cancelled")
    visual._capture(page, "23-recurring-management")


hardened._delivery_closure = _delivery_closure_with_recurring


if __name__ == "__main__":
    hardened._preserve_playwright_browser_cache()
    acceptance.main()
