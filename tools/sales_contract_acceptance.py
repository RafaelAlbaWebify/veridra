from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import operator_e2e_acceptance as base
from playwright.sync_api import Page, sync_playwright


def _write_report(report: dict[str, Any], output: Path) -> None:
    report["checkpoint_at"] = datetime.now(UTC).isoformat()
    (output / "acceptance.json").write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _checkpoint(report: dict[str, Any], output: Path, name: str) -> None:
    report["current_step"] = name
    _write_report(report, output)
    print(f"[#285] {name}", flush=True)


def _copy_runtime_logs(env: dict[str, str], output: Path) -> None:
    localapp = env.get("LOCALAPPDATA", "").strip()
    if not localapp:
        return
    runtime = Path(localapp) / "Veridra" / "runtime"
    if not runtime.exists():
        return
    for source in runtime.glob("*.log"):
        try:
            shutil.copy2(source, output / source.name)
        except OSError:
            continue


def _launcher(repo: Path, env: dict[str, str], command: str) -> None:
    """Run the supported launcher without inheritable stdout/stderr pipes.

    On Windows, a captured pipe can remain open in descendants started by PowerShell,
    which makes subprocess.run()/communicate wait even after the launcher has finished.
    VERIDRA already writes managed-process output to its runtime log files, so the
    acceptance runner deliberately discards the wrapper process streams and preserves
    those authoritative runtime logs on failure instead.
    """
    script = repo / "scripts" / "windows" / "veridra-local.ps1"
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            command,
        ],
        cwd=repo,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    try:
        returncode = process.wait(timeout=60)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.wait(timeout=10)
        raise RuntimeError(f"VERIDRA launcher {command!r} timed out.") from exc
    if returncode != 0:
        raise RuntimeError(f"VERIDRA launcher {command!r} failed ({returncode}).")


def _capture(report: dict[str, Any], page: Page, evidence: Path, name: str) -> None:
    screenshot = evidence / f"{name}.png"
    text_path = evidence / f"{name}.txt"
    page.screenshot(path=str(screenshot), full_page=True)
    visible = page.locator("body").inner_text()
    text_path.write_text(visible, encoding="utf-8")
    report["steps"].append(
        {
            "name": name,
            "url": page.url,
            "title": page.title(),
            "screenshot": screenshot.name,
            "visible_text": text_path.name,
        }
    )
    _write_report(report, evidence)


def _create_and_qualify_prospect(
    page: Page,
    base_url: str,
    report: dict[str, Any],
    evidence: Path,
) -> str:
    page.goto(f"{base_url}/agency/prospects/new", wait_until="domcontentloaded")
    _capture(report, page, evidence, "00-add-prospect-form")
    base._assert_text(page, "Add prospect")
    values = {
        "business_name": base.BUSINESS,
        "website": base.TARGET,
        "sector": "Dental clinic",
        "phone": "+35315550100",
        "locality": "Dublin",
        "administrative_area": "Dublin",
        "country_code": "IE",
        "contact_email": "acceptance@example.com",
        "evidence_summary": "Synthetic #285 sales-contract acceptance fixture. No real outreach.",
    }
    for name, value in values.items():
        page.locator(f"[name='{name}']").fill(value)
    page.get_by_role("button", name="Create prospect").click()
    page.wait_for_url("**/agency/prospects/*")
    prospect_url = page.url
    base._assert_text(page, base.BUSINESS)

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
        "Synthetic acceptance prospect intentionally qualifies for the sales workflow."
    )
    page.get_by_role("button", name="Save qualification").click()
    page.wait_for_url(prospect_url)
    page.wait_for_load_state("domcontentloaded")
    base._assert_text(page, "14/14")
    return prospect_url


def _set_reply(page: Page, prospect_url: str, outcome: str) -> None:
    page.goto(f"{prospect_url}/deal", wait_until="domcontentloaded")
    page.locator("select[name='reply_outcome']").select_option(outcome)
    page.locator("textarea[name='conversation_summary']").fill(
        f"Synthetic {outcome} reply for #285 browser acceptance."
    )
    page.locator("input[name='next_action']").fill("")
    page.get_by_role("button", name="Save reply context").click()
    page.wait_for_url(f"{prospect_url}/deal")


def _next_action(page: Page) -> str:
    return page.locator("input[name='next_action']").input_value().lower()


def _discovery(page: Page, prospect_url: str) -> None:
    page.goto(f"{prospect_url}/deal", wait_until="domcontentloaded")
    form = page.locator(f"form[action='{prospect_url.replace(page.url.split('/agency/prospects/')[0], '')}/deal/discovery']")
    if form.count() != 1:
        form = page.locator("form[action$='/deal/discovery']")
    values = {
        "goals": "Reduce mobile booking friction and improve trust.",
        "current_platform": "WordPress",
        "hosting": "External managed host",
        "decision_maker": "Clinic owner",
        "urgency": "This month",
        "constraints": "No booking-platform replacement.",
        "access_readiness": "Admin access available after booking.",
        "measurable_scope": "Fix agreed mobile and trust issues on the current site.",
        "deliverables": "Bounded fixes, verification and final report.",
        "exclusions": "Copywriting and booking-system replacement.",
        "assumptions": "Existing hosting remains in place.",
        "timeline": "5 business days after access",
    }
    for name, value in values.items():
        form.locator(f"[name='{name}']").fill(value)
    form.get_by_role("button", name="Save discovery").click()
    page.wait_for_url(f"{prospect_url}/deal")


def _create_proposal(
    page: Page,
    prospect_url: str,
    *,
    title: str,
    price: str,
    recurring: bool = True,
) -> int:
    page.goto(f"{prospect_url}/deal", wait_until="domcontentloaded")
    before = page.locator("div.proposal").count()
    page.locator("input[name='title']").fill(title)
    page.locator("textarea[name='scope']").last.fill(
        "Fix agreed mobile and trust issues on the current site."
    )
    page.locator("textarea[name='deliverables']").last.fill(
        "Bounded fixes, verification and final report."
    )
    page.locator("textarea[name='exclusions']").last.fill(
        "Copywriting and booking-system replacement."
    )
    page.locator("textarea[name='assumptions']").last.fill(
        "Existing hosting remains in place."
    )
    page.locator("input[name='timeline']").last.fill("5 business days after access")
    valid_until = (datetime.now(UTC).date() + timedelta(days=14)).isoformat()
    page.locator("input[name='valid_until']").fill(valid_until)
    page.locator("input[name='price_amount']").fill(price)
    page.locator("input[name='currency']").fill("EUR")
    if recurring:
        page.locator("input[name='recurring_amount']").fill("99.00")
        page.locator("input[name='recurring_cadence']").fill("monthly")
    page.get_by_role("button", name="Create proposal version").click()
    page.wait_for_url(f"{prospect_url}/deal")
    after = page.locator("div.proposal").count()
    if after != before + 1:
        raise AssertionError("Proposal version was not visibly created through the UI.")
    return after


def _proposal_status(
    page: Page,
    prospect_url: str,
    version: int,
    status: str,
    acceptance_reference: str = "",
) -> None:
    page.goto(f"{prospect_url}/deal", wait_until="domcontentloaded")
    form = page.locator(f"form[action$='/deal/proposals/{version}/status']")
    form.locator("select[name='status']").select_option(status)
    form.locator("input[name='acceptance_reference']").fill(acceptance_reference)
    form.get_by_role("button", name="Update proposal status").click()
    page.wait_for_url(f"{prospect_url}/deal")


def _scope_change(page: Page, prospect_url: str, resulting_version: int) -> None:
    url = f"{prospect_url}/deal/change-requests"
    page.goto(url, wait_until="domcontentloaded")
    page.locator("textarea[name='summary']").fill(
        "Add a second booking form to the agreed sprint."
    )
    page.locator("textarea[name='scope_impact']").fill(
        "Adds one form implementation and verification step."
    )
    page.locator("input[name='price_impact']").fill("+ EUR 150")
    page.locator("input[name='timeline_impact']").fill("+ 1 business day")
    page.get_by_role("button", name="Record change request").click()
    page.wait_for_url(url)

    form = page.locator("form[action$='/change-requests/1/status']")
    form.locator("select[name='status']").select_option("approved")
    form.locator("input[name='decision_reference']").fill(
        "Synthetic customer approval of scope change."
    )
    form.get_by_role("button", name="Update change request").click()
    page.wait_for_url(url)

    form = page.locator("form[action$='/change-requests/1/status']")
    form.locator("select[name='status']").select_option("incorporated")
    form.locator("input[name='resulting_proposal_version']").fill(str(resulting_version))
    form.get_by_role("button", name="Update change request").click()
    page.wait_for_url(url)
    base._assert_text(page, "incorporated")


def run() -> Path:
    if os.name != "nt":
        raise SystemExit("#285 sales-contract acceptance must run on Windows.")
    repo = Path(__file__).resolve().parents[1]
    output = repo / "artifacts" / "sales-contract-acceptance"
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    report: dict[str, Any] = {
        "contract": "veridra_sales_contract_acceptance",
        "version": "1.5",
        "started_at": datetime.now(UTC).isoformat(),
        "passed": False,
        "steps": [],
        "checks": {},
    }
    _checkpoint(report, output, "initialised")

    with tempfile.TemporaryDirectory(prefix="veridra-sales-contract-") as temporary:
        temp = Path(temporary)
        localapp = temp / "LocalAppData"
        localapp.mkdir(parents=True)
        port = base._free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["LOCALAPPDATA"] = str(localapp)
        env["VERIDRA_LOCAL_PORT"] = str(port)
        started = False
        try:
            _checkpoint(report, output, "starting supported launcher")
            _launcher(repo, env, "start")
            started = True
            _checkpoint(report, output, "launcher started")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1440, "height": 1000})
                page = context.new_page()
                page.set_default_timeout(15_000)
                page.set_default_navigation_timeout(20_000)

                _checkpoint(report, output, "onboarding")
                base._onboard(page, base_url)
                base._enable_agency_plan(page, base_url)
                prospect_url = _create_and_qualify_prospect(page, base_url, report, output)
                _capture(report, page, output, "01-qualified-prospect")

                _set_reply(page, prospect_url, "price_request")
                if "before quoting" not in _next_action(page):
                    raise AssertionError("Price request did not produce a safe next action.")
                _capture(report, page, output, "02-price-request")
                report["checks"]["price_request_branch"] = True

                _set_reply(page, prospect_url, "call_request")
                if "discovery call" not in _next_action(page):
                    raise AssertionError(
                        "Call request did not produce a discovery-call next action."
                    )
                _capture(report, page, output, "03-call-request")
                report["checks"]["call_request_branch"] = True

                _set_reply(page, prospect_url, "different_scope")
                if "assess fit" not in _next_action(page):
                    raise AssertionError(
                        "Different-scope reply did not produce fit assessment."
                    )
                _capture(report, page, output, "04-different-scope-request")
                report["checks"]["different_scope_branch"] = True

                _set_reply(page, prospect_url, "positive")
                _capture(report, page, output, "05-positive-reply")
                _discovery(page, prospect_url)
                _capture(report, page, output, "06-discovery-complete")
                report["checks"]["discovery_completed_in_ui"] = True

                version1 = _create_proposal(
                    page,
                    prospect_url,
                    title="Website Improvement Sprint",
                    price="650.00",
                )
                _capture(report, page, output, "07-proposal-v1-draft")
                _proposal_status(page, prospect_url, version1, "sent")
                _capture(report, page, output, "08-proposal-v1-sent")
                _proposal_status(
                    page,
                    prospect_url,
                    version1,
                    "accepted",
                    "Synthetic customer accepted proposal v1 externally.",
                )
                base._assert_text(page, "Proposal accepted")
                base._assert_text(page, "agreement and payment evidence before work starts")
                _capture(report, page, output, "09-proposal-v1-accepted")
                report["checks"]["accepted_proposal_stops_before_payment_gate"] = True

                artifact_url = f"{prospect_url}/deal/proposals/{version1}/artifact"
                page.goto(artifact_url, wait_until="domcontentloaded")
                base._assert_text(page, "Webify Digital Solutions")
                base._assert_text(page, "EUR 650.00")
                base._assert_text(page, "not an accounting invoice")
                _capture(report, page, output, "10-proposal-artifact")
                report["checks"]["proposal_artifact_visible"] = True

                version2 = _create_proposal(
                    page,
                    prospect_url,
                    title="Alternative Scope",
                    price="500.00",
                    recurring=False,
                )
                _proposal_status(page, prospect_url, version2, "sent")
                _proposal_status(page, prospect_url, version2, "declined")
                _capture(report, page, output, "11-proposal-v2-declined")
                report["checks"]["decline_branch"] = True

                version3 = _create_proposal(
                    page,
                    prospect_url,
                    title="Scope Change Revision",
                    price="800.00",
                )
                _scope_change(page, prospect_url, version3)
                _capture(report, page, output, "12-scope-change-incorporated")
                report["checks"]["scope_change_branch"] = True

                page.goto(f"{base_url}/agency/deals", wait_until="domcontentloaded")
                base._assert_text(page, base.BUSINESS)
                base._assert_text(page, "Sales / proposals")
                _capture(report, page, output, "13-sales-workbench")
                report["checks"]["sales_workbench_visible"] = True

                context.close()
                browser.close()

            report["passed"] = True
            report["current_step"] = "complete"
        except Exception as exc:
            report["failure"] = f"{type(exc).__name__}: {exc}"
            _copy_runtime_logs(env, output)
            _write_report(report, output)
            print(f"[#285][FAIL] {report['failure']}", flush=True)
            raise
        finally:
            if started:
                try:
                    _checkpoint(report, output, "stopping supported launcher")
                    _launcher(repo, env, "stop")
                except Exception as exc:  # pragma: no cover - diagnostic cleanup path
                    report["cleanup_error"] = str(exc)
                    _copy_runtime_logs(env, output)

    report["finished_at"] = datetime.now(UTC).isoformat()
    _write_report(report, output)
    print(f"[PASS] #285 sales-contract acceptance: {output}", flush=True)
    return output


if __name__ == "__main__":
    run()
