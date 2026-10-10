"""Read-only Chromium acceptance using the operator's actual saved Market Study JSON.

Runs a local, isolated page with the application's actual HTML and JavaScript.
No HTTP server, authentication session, data changes, or external network access.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import Request
from playwright.sync_api import Route, sync_playwright

from veridra import agency_prospect_discovery_web as web
from veridra.agency_market_study import market_detail
from veridra.market_intelligence import load


def main() -> None:
    root = Path(os.environ["VERIDRA_TENANT_DATA_ROOT"]).resolve()
    paths = sorted((root / "_market_studies").glob("*/*.json"))
    if not paths:
        raise SystemExit("FAIL: No persisted Market Studies in configured tenant data root")
    report_dir = Path("artifacts/market-operator-visual")
    report_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for index, path in enumerate(paths):
                study = load(path)
                expected = len(study.businesses)
                if expected == 0:
                    raise AssertionError("Market Study has no businesses: " + study.study_id)
                page_html = market_detail(study)
                original = web._market_study
                try:
                    web._market_study = lambda _request, _id: study
                    request = Request({"type": "http", "method": "GET", "path": "/test", "headers": []})
                    script = bytes(web.market_selection_script(study.study_id, request).body).decode("utf-8")
                finally:
                    web._market_study = original
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                try:
                    url = "https://veridra.test/agency/prospects/discover/market/" + study.study_id

                    def isolated(route: Route) -> None:
                        if route.request.method != "GET":
                            raise AssertionError("Unexpected write request: " + route.request.url)
                        if route.request.url.endswith("/selection.js"):
                            route.fulfill(status=200, content_type="application/javascript", body=script)
                        elif route.request.url.endswith("/map-view"):
                            route.fulfill(status=200, content_type="text/html", body="<html><body>Map view isolated</body></html>")
                        elif route.request.url == url:
                            route.fulfill(status=200, content_type="text/html", body=page_html, headers={
                                "content-security-policy": "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-src 'self'"
                            })
                        else:
                            route.abort()

                    page.route("**/*", isolated)
                    page.goto(url)
                    page.locator("details.market-bottom > summary").click()
                    rows = page.locator(".market-business-row:visible")
                    if rows.count() != expected:
                        raise AssertionError(f"Rendered {rows.count()} of {expected} saved businesses")
                    for selector in ("#market-business-prequalification", "#market-business-website",
                                     "#market-business-search", "#market-business-count"):
                        if page.locator(selector).count() != 1:
                            raise AssertionError("Missing market control " + selector)
                    if page.get_by_role("columnheader", name="Website audit").count() != 1:
                        raise AssertionError("Website audit column missing")
                    if page.get_by_role("columnheader", name="Prequalification").count() != 1:
                        raise AssertionError("Prequalification column missing")
                    page.locator("#market-business-prequalification").select_option("needs-verification")
                    filtered = rows.count()
                    if filtered > expected:
                        raise AssertionError("Prequalification filter increased row count")
                    page.get_by_role("button", name="Reset filters").click()
                    if rows.count() != expected:
                        raise AssertionError("Filter reset failed to restore all businesses")
                    screenshot = report_dir / f"study-{index + 1}.png"
                    page.screenshot(path=str(screenshot), full_page=False)
                    results.append({"study": study.study_id, "businesses": expected,
                                    "filtered_needs_verification": filtered,
                                    "screenshot": str(screenshot), "result": "PASS"})
                    print(f"PASS study {index + 1}: {expected} businesses; filters and audit column visible")
                finally:
                    page.close()
        finally:
            browser.close()
    (report_dir / "result.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("PASS: real saved Market Study browser rendering, read-only.")


if __name__ == "__main__":
    main()
