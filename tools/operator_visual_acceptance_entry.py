# ruff: noqa: I001,E501
from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import operator_e2e_acceptance as acceptance
import operator_e2e_acceptance_entry as hardened
from playwright.sync_api import Page
from veridra.ai_review_exchange import result_integrity_hash


VISUAL_ROOT = Path("artifacts/operator-visual")
VISUAL_ROOT.mkdir(parents=True, exist_ok=True)


CORE_GUIDANCE: dict[str, tuple[str, ...]] = {
    "04-new-prospect-form": ("Create prospect",),
    "05-qualified-prospect": ("Next action", "Run prospect audit"),
    "07-customer-created": ("Work blocked", "Next action"),
    "08-customer-onboarded": ("Work may start", "Create and link project"),
    "09-linked-project": ("Recommended next step", "Run first assessment"),
    "10-first-assessment-saved": ("Recommended next step", "Review saved findings"),
    "10-monitoring-after-assessment": ("Latest assessment", "Run monitoring check now"),
    "12-remediation-task": ("Task status is an explicit operator decision",),
    "13-report-delivery-status": ("Report delivery status", "Record external delivery"),
    "13b-report-hub": ("Preview branded HTML", "Download PDF"),
    "14-monitoring-configured": ("Monitoring configuration saved", "Run monitoring check now"),
    "15-progress-changes": ("Progress / Changes", "Latest"),
    "16-customer-billing-paid": ("Billing", "Paid"),
    "16-customer-billing-mutated-after-backup": ("Billing",),
    "17-delivery-closed-recurring-accepted": ("Project closed", "Recurring service: Accepted"),
    "18-recurring-draft": ("Configure recurring plan",),
    "19-recurring-active": ("Recurring operations",),
    "20-recurring-payment-blocked": ("Service is payment-blocked",),
    "21-recurring-renewed": ("Renew / change recurring plan", "Version:"),
    "22-recurring-cancelled": ("Recurring service is cancelled",),
    "23-recurring-management": ("Presence Care", "Next action"),
}


def _guidance_for(name: str) -> tuple[str, ...]:
    if name.startswith("06-commercial-"):
        return ("Next action", "Save commercial progress")
    return CORE_GUIDANCE.get(name, ())


def _assert_semantic_guidance(name: str, visible: str) -> None:
    expected = _guidance_for(name)
    if not expected:
        return
    missing = [item for item in expected if item not in visible]
    result = {
        "checkpoint": name,
        "expected_visible_guidance": list(expected),
        "passed": not missing,
        "missing": missing,
    }
    (VISUAL_ROOT / f"{name}.semantic.json").write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )
    if missing:
        raise AssertionError(
            f"CORE checkpoint {name!r} is missing visible guidance: "
            + ", ".join(missing)
        )


def _capture(page: Page, name: str) -> None:
    """Capture viewport/full-page evidence plus layout metrics for visual review."""
    VISUAL_ROOT.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(VISUAL_ROOT / f"{name}.png"), full_page=False)
    page.screenshot(path=str(VISUAL_ROOT / f"{name}-full.png"), full_page=True)
    visible = page.locator("body").inner_text(timeout=10_000)
    (VISUAL_ROOT / f"{name}.txt").write_text(visible, encoding="utf-8")
    metrics = page.evaluate(
        """() => {
            const root = document.documentElement;
            const body = document.body;
            const workbench = document.querySelector('.agency-workbench');
            const main = document.querySelector('main');
            const rect = (el) => el ? el.getBoundingClientRect() : null;
            const viewport = {width: window.innerWidth, height: window.innerHeight};
            const overflowX = Math.max(root.scrollWidth, body.scrollWidth) > viewport.width + 1;
            const overflowY = Math.max(root.scrollHeight, body.scrollHeight) > viewport.height + 1;
            const interactive = [...document.querySelectorAll(
                'button, a, input, select, textarea, summary'
            )];
            const clipped = interactive
                .map((el) => {
                    const r = el.getBoundingClientRect();
                    return {
                        tag: el.tagName,
                        text: (el.innerText || el.getAttribute('aria-label') || el.name || '')
                            .trim().slice(0, 120),
                        left: r.left,
                        top: r.top,
                        right: r.right,
                        bottom: r.bottom,
                        width: r.width,
                        height: r.height,
                    };
                })
                .filter((r) =>
                    r.width > 0 &&
                    r.height > 0 &&
                    (r.left < -1 || r.right > viewport.width + 1)
                );
            const internalScrollers = [...document.querySelectorAll(
                '.workbench-scroll, .workbench-pane, .workbench-cards'
            )].map((el) => ({
                className: el.className,
                clientHeight: el.clientHeight,
                scrollHeight: el.scrollHeight,
                clientWidth: el.clientWidth,
                scrollWidth: el.scrollWidth,
                verticalScroll: el.scrollHeight > el.clientHeight + 1,
                horizontalScroll: el.scrollWidth > el.clientWidth + 1,
            }));
            return {
                url: location.href,
                title: document.title,
                viewport,
                document: {
                    scrollWidth: Math.max(root.scrollWidth, body.scrollWidth),
                    scrollHeight: Math.max(root.scrollHeight, body.scrollHeight),
                    overflowX,
                    overflowY,
                },
                bodyOverflow: getComputedStyle(body).overflow,
                main: rect(main),
                workbench: rect(workbench),
                clippedInteractive: clipped,
                internalScrollers,
            };
        }"""
    )
    (VISUAL_ROOT / f"{name}.layout.json").write_text(
        json.dumps(metrics, indent=2),
        encoding="utf-8",
    )


_ORIGINAL_STEP = acceptance._step
_ORIGINAL_CREATE_AND_QUALIFY = acceptance._create_and_qualify_prospect
_ORIGINAL_COMMERCIAL_STAGE = acceptance._commercial_stage
_ORIGINAL_OPEN_CUSTOMER = acceptance._open_customer
_ORIGINAL_COMPLETE_ONBOARDING = acceptance._complete_onboarding
_ORIGINAL_CREATE_LINKED_PROJECT = acceptance._create_linked_project
_ORIGINAL_REMEDIATION = acceptance._remediation
_ORIGINAL_REPORT = acceptance._report
_ORIGINAL_CONFIGURE_MONITORING = acceptance._configure_autonomous_monitoring
_ORIGINAL_WAIT_MONITORING = acceptance._wait_autonomous_monitoring
_ORIGINAL_BILLING = acceptance._billing


def _step(report: dict[str, object], page: Page, evidence: Path, name: str) -> None:
    _ORIGINAL_STEP(report, page, evidence, name)
    _capture(page, f"core-{name}")


def _create_and_qualify_prospect(page: Page, base_url: str) -> str:
    page.goto(f"{base_url}/agency/prospects/new", wait_until="networkidle")
    _capture(page, "04-new-prospect-form")
    prospect_url = _ORIGINAL_CREATE_AND_QUALIFY(page, base_url)
    _capture(page, "05-qualified-prospect")
    return prospect_url


def _commercial_stage(page: Page, prospect_url: str, stage: str, note: str) -> None:
    _ORIGINAL_COMMERCIAL_STAGE(page, prospect_url, stage, note)
    _capture(page, f"06-commercial-{stage}")


def _open_customer(page: Page, base_url: str) -> str:
    customer_url = _ORIGINAL_OPEN_CUSTOMER(page, base_url)
    _capture(page, "07-customer-created")
    return customer_url


def _complete_onboarding(page: Page, customer_url: str) -> None:
    _ORIGINAL_COMPLETE_ONBOARDING(page, customer_url)
    _capture(page, "08-customer-onboarded")


def _create_linked_project(page: Page, customer_url: str) -> str:
    project_url = _ORIGINAL_CREATE_LINKED_PROJECT(page, customer_url)
    _capture(page, "09-linked-project")
    return project_url


def _synthetic_review_result(bundle: dict[str, object]) -> dict[str, object]:
    evidence = bundle.get("evidence", [])
    evidence_ref = ""
    if isinstance(evidence, list) and evidence and isinstance(evidence[0], dict):
        evidence_ref = str(evidence[0].get("evidence_id", ""))
    evidence_refs = [evidence_ref] if evidence_ref else []
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "exchange_type": "veridra_ai_review_result",
        "review_id": "review-e2e-standard-exchange",
        "source_bundle_id": bundle["bundle_id"],
        "source_bundle_hash_sha256": bundle["bundle_hash_sha256"],
        "generated_at": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
        "model_provenance": "Synthetic Playwright acceptance fixture",
        "tool_provenance": "VERIDRA visual acceptance",
        "interpretation": "Synthetic review reasoning used only to validate the operator exchange workflow.",
        "strengths": ["The imported reasoning is bound to the exported VERIDRA evidence bundle."],
        "weaknesses_gaps": ["No business outcome is inferred from this synthetic review."],
        "opportunity_assessment": "Operator review remains required before any remediation or outreach decision.",
        "confidence": "high",
        "uncertainty": ["This acceptance fixture does not estimate traffic, ranking, revenue or conversion impact."],
        "recommended_next_action": "Verify the cited deterministic evidence before deciding any action.",
        "suggested_messaging_positioning": ["Use only directly observed evidence; do not claim unmeasured business impact."],
        "evidence_refs": evidence_refs,
        "safe_actions": [
            {
                "action": "request_human_review",
                "reason": "Human verification is required before acting on imported reasoning.",
                "evidence_refs": evidence_refs,
            }
        ],
    }
    payload["result_hash_sha256"] = result_integrity_hash(payload)
    return payload


def _ai_review_exchange(page: Page, project_url: str) -> None:
    page.goto(f"{project_url}/ai-review", wait_until="networkidle")
    _capture(page, "11a-ai-review-exchange-empty")
    with page.expect_download(timeout=30_000) as download_info:
        page.get_by_role("link", name="Export AI review JSON").click()
    download = download_info.value
    exported = VISUAL_ROOT / "AI_REVIEW_EXPORT.json"
    download.save_as(exported)
    bundle = json.loads(exported.read_text(encoding="utf-8"))
    result = _synthetic_review_result(bundle)
    page.goto(f"{project_url}/ai-review/import", wait_until="networkidle")
    _capture(page, "11b-ai-review-import-form")
    page.get_by_label("Reviewed result JSON").fill(json.dumps(result))
    page.get_by_role("button", name="Validate and import").click()
    page.wait_for_url("**/ai-review?imported=true", timeout=15_000)
    acceptance._assert_text(page, "Reviewed result imported")
    _capture(page, "11c-ai-review-exchange-imported")
    page.get_by_role("link", name="review-e2e-standard-exchange").click()
    page.wait_for_load_state("networkidle")
    acceptance._assert_text(page, "AI interpretation")
    acceptance._assert_text(page, "imported reasoning, not VERIDRA observation")
    acceptance._assert_text(page, "No outreach has been sent")
    _capture(page, "11-ai-review-imported-result")


def _manual_assessment(page: Page, project_url: str) -> str:
    page.goto(project_url, wait_until="networkidle")
    page.get_by_role("button", name="Run first assessment").click()
    page.wait_for_url("**/agency/projects/*?assessment_id=*", timeout=120_000)
    page.wait_for_load_state("networkidle", timeout=120_000)
    if "assessment_id=" not in page.url:
        raise AssertionError("First project assessment did not expose a saved assessment id.")
    acceptance._assert_text(page, "Saved assessment", timeout=120_000)
    _capture(page, "10-first-assessment-saved")

    project_tools = page.locator("details", has_text="Other project tools")
    project_tools.locator("summary").click()
    project_tools.locator("a[href$='/monitoring']").click()
    page.wait_for_url("**/monitoring", timeout=15_000)
    page.wait_for_load_state("networkidle")
    monitoring_url = page.url
    acceptance._assert_text(page, "Latest assessment")
    _capture(page, "10-monitoring-after-assessment")

    _ai_review_exchange(page, project_url)
    page.goto(monitoring_url, wait_until="networkidle")
    return monitoring_url


def _remediation(page: Page, project_url: str) -> None:
    _ORIGINAL_REMEDIATION(page, project_url)
    _capture(page, "12-remediation-task")


def _report(page: Page, project_url: str, evidence: Path) -> None:
    _ORIGINAL_REPORT(page, project_url, evidence)
    _capture(page, "13-report-delivery-status")
    page.goto(f"{project_url}/reports", wait_until="networkidle")
    _capture(page, "13b-report-hub")
    edit_link = page.get_by_role("link", name="Edit current saved profile")
    if edit_link.count() == 1:
        edit_link.click()
        page.wait_for_load_state("networkidle")
        _capture(page, "13c-report-profile")
    report_pdf = evidence / "VERIDRA_E2E_REPORT.pdf"
    if report_pdf.exists():
        shutil.copy2(report_pdf, VISUAL_ROOT / "VERIDRA_E2E_REPORT.pdf")
        (VISUAL_ROOT / "report-path.json").write_text(
            json.dumps({"report_pdf": str(report_pdf)}, indent=2),
            encoding="utf-8",
        )


def _configure_autonomous_monitoring(page: Page, monitoring_url: str) -> None:
    _ORIGINAL_CONFIGURE_MONITORING(page, monitoring_url)
    _capture(page, "14-monitoring-configured")


def _wait_autonomous_monitoring(runtime_log: Path, page: Page, monitoring_url: str) -> None:
    _ORIGINAL_WAIT_MONITORING(runtime_log, page, monitoring_url)
    _capture(page, "15-progress-changes")


def _billing(page: Page, customer_url: str, note: str) -> None:
    _ORIGINAL_BILLING(page, customer_url, note)
    suffix = "mutated-after-backup" if note == acceptance.MUTATED_BILLING_NOTE else "paid"
    _capture(page, f"16-customer-billing-{suffix}")


acceptance._step = _step
acceptance._create_and_qualify_prospect = _create_and_qualify_prospect
acceptance._commercial_stage = _commercial_stage
acceptance._open_customer = _open_customer
acceptance._complete_onboarding = _complete_onboarding
acceptance._create_linked_project = _create_linked_project
acceptance._manual_assessment = _manual_assessment
acceptance._remediation = _remediation
acceptance._report = _report
acceptance._configure_autonomous_monitoring = _configure_autonomous_monitoring
acceptance._wait_autonomous_monitoring = _wait_autonomous_monitoring
acceptance._billing = _billing


if __name__ == "__main__":
    hardened._preserve_playwright_browser_cache()
    acceptance.main()
