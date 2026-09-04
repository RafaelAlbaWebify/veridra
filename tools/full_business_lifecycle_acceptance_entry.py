# ruff: noqa: E501,I001,F401
from __future__ import annotations

import operator_e2e_acceptance as acceptance
import operator_e2e_acceptance_entry as hardened
import operator_recurring_visual_acceptance_entry as recurring
import operator_visual_acceptance_entry as visual
import sales_contract_acceptance as sales
from playwright.sync_api import Page


_VISUAL_CREATE_AND_QUALIFY = acceptance._create_and_qualify_prospect
_ORIGINAL_ONBOARDING = hardened._ORIGINAL_COMPLETE_ONBOARDING
_VISUAL_REMEDIATION = acceptance._remediation


def _sales_cycle_create_and_qualify(page: Page, base_url: str) -> str:
    """Run #285 reply/discovery/proposal branches before continuing the same customer state."""
    prospect_url = _VISUAL_CREATE_AND_QUALIFY(page, base_url)

    sales._set_reply(page, prospect_url, "price_request")
    if "before quoting" not in sales._next_action(page):
        raise AssertionError("Price request did not produce the bounded pre-quote next action.")
    visual._capture(page, "05a-price-request")

    sales._set_reply(page, prospect_url, "call_request")
    if "discovery call" not in sales._next_action(page):
        raise AssertionError("Call request did not produce a discovery-call next action.")
    visual._capture(page, "05b-call-request")

    sales._set_reply(page, prospect_url, "different_scope")
    if "assess fit" not in sales._next_action(page):
        raise AssertionError("Different-scope request did not produce a fit assessment.")
    visual._capture(page, "05c-different-scope-request")

    sales._set_reply(page, prospect_url, "positive")
    visual._capture(page, "05d-positive-reply")
    sales._discovery(page, prospect_url)
    acceptance._assert_text(page, "Discovery")
    visual._capture(page, "05e-discovery-complete")

    version1 = sales._create_proposal(
        page,
        prospect_url,
        title="Website Improvement Sprint",
        price="650.00",
    )
    sales._proposal_status(page, prospect_url, version1, "sent")
    sales._proposal_status(
        page,
        prospect_url,
        version1,
        "accepted",
        "Synthetic customer accepted proposal v1 externally.",
    )
    acceptance._assert_text(page, "Proposal accepted")
    acceptance._assert_text(page, "agreement and payment evidence before work starts")
    visual._capture(page, "05f-proposal-accepted")

    page.goto(
        f"{prospect_url}/deal/proposals/{version1}/artifact",
        wait_until="networkidle",
    )
    acceptance._assert_text(page, "Webify Digital Solutions")
    acceptance._assert_text(page, "EUR 650.00")
    acceptance._assert_text(page, "not an accounting invoice")
    visual._capture(page, "05g-proposal-artifact")

    version2 = sales._create_proposal(
        page,
        prospect_url,
        title="Alternative Scope",
        price="500.00",
        recurring=False,
    )
    sales._proposal_status(page, prospect_url, version2, "sent")
    sales._proposal_status(page, prospect_url, version2, "declined")
    visual._capture(page, "05h-proposal-declined")

    version3 = sales._create_proposal(
        page,
        prospect_url,
        title="Scope Change Revision",
        price="800.00",
    )
    sales._scope_change(page, prospect_url, version3)
    visual._capture(page, "05i-prebooking-scope-change")

    page.goto(f"{base_url}/agency/deals", wait_until="networkidle")
    acceptance._assert_text(page, "Sales / proposals")
    acceptance._assert_text(page, acceptance.BUSINESS)
    visual._capture(page, "05j-sales-workbench")
    return prospect_url


def _complete_onboarding_full_cycle(page: Page, customer_url: str) -> None:
    """Prove accepted-but-unpaid and paid-but-access-delayed gates in the same customer."""
    page.goto(customer_url, wait_until="networkidle")
    acceptance._assert_text(page, "Work blocked")

    page.get_by_label("Terms / agreement reference").fill("WEBIFY-MSA-E2E")
    page.get_by_label("Terms version").fill("2026-09")
    page.get_by_label("Accepted at").fill("2026-09-04T10:00")
    page.get_by_label("External signature reference").fill("SIGN-E2E-001")
    page.get_by_label("Acceptance evidence").fill(
        "Synthetic accepted-terms evidence for #289 full-cycle acceptance."
    )
    page.get_by_label("Billing status").select_option("issued")
    page.get_by_label("External invoice reference").fill(acceptance.INVOICE)
    page.get_by_label("Invoice amount").fill("650.00")
    page.get_by_label("Currency").fill("EUR")
    page.get_by_label("Issued on").fill("2026-09-04")
    page.get_by_label("Due on").fill("2026-09-18")
    page.get_by_label("Deposit / upfront payment required before work").check()
    page.get_by_label("Required upfront amount").fill("325.00")
    page.get_by_role("button", name="Save customer").click()
    page.wait_for_url(customer_url)
    acceptance._assert_text(page, "Work blocked")
    acceptance._assert_text(page, "Waiting for required payment evidence")
    if page.get_by_role("button", name="Create and link project").count() != 0:
        raise AssertionError("Project creation was exposed for accepted-but-unpaid customer.")
    visual._capture(page, "07a-accepted-unpaid-blocked")

    page.get_by_label("Billing status").select_option("partially_paid")
    page.get_by_label("Amount paid").fill("325.00")
    page.get_by_label("Payment evidence reference").fill("PAY-E2E-DEPOSIT-001")
    page.get_by_label("Payment method reference").fill("bank transfer")
    page.get_by_label("Provider transaction reference").fill("BANK-E2E-001")
    page.get_by_role("button", name="Save customer").click()
    page.wait_for_url(customer_url)
    acceptance._assert_text(page, "Work may start")
    page.get_by_role("button", name="Create and link project").wait_for(state="visible")

    access = page.get_by_label("Access/domain/hosting requirements confirmed")
    if access.is_checked():
        raise AssertionError("Access readiness unexpectedly completed before customer access handoff.")
    acceptance._assert_text(page, "Onboarding")
    visual._capture(page, "07b-paid-access-delayed")

    _ORIGINAL_ONBOARDING(page, customer_url)
    acceptance._assert_text(page, "Onboarding: 5/5")
    acceptance._assert_text(page, "Status: Active")
    visual._capture(page, "08-customer-onboarded")


def _remediation_with_blocked_branch(page: Page, project_url: str) -> None:
    """Exercise remediation blocked/unavailable state before resuming delivery."""
    _VISUAL_REMEDIATION(page, project_url)
    page.goto(f"{project_url}/tasks", wait_until="networkidle")
    page.get_by_role("link", name="Open task").first.click()
    page.wait_for_load_state("networkidle")
    status = page.get_by_label("Status")
    status.select_option("blocked")
    page.get_by_label("Notes").fill(
        "Synthetic dependency unavailable; remediation temporarily blocked."
    )
    page.get_by_role("button", name="Save task").click()
    page.wait_for_url("**/tasks")
    acceptance._assert_text(page, "blocked")
    visual._capture(page, "12a-remediation-blocked")

    page.get_by_role("link", name="Open task").first.click()
    page.wait_for_load_state("networkidle")
    page.get_by_label("Status").select_option("in_progress")
    page.get_by_label("Notes").fill(
        "Synthetic dependency restored; remediation resumed for acceptance."
    )
    page.get_by_role("button", name="Save task").click()
    page.wait_for_url("**/tasks")
    visual._capture(page, "12b-remediation-resumed")


# Importing the recurring entry installs the delivery->recurring lifecycle monkeypatch.
# Replace only the earlier phases so one supported Windows run now spans reply through exit.
acceptance._create_and_qualify_prospect = _sales_cycle_create_and_qualify
acceptance._complete_onboarding = _complete_onboarding_full_cycle
acceptance._remediation = _remediation_with_blocked_branch


if __name__ == "__main__":
    hardened._preserve_playwright_browser_cache()
    acceptance.main()
