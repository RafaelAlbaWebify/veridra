# ruff: noqa: E501
"""Real Chromium regression: CSP and every sector toolbar control."""
from __future__ import annotations

from urllib.parse import parse_qs

import pytest
from fastapi import Request
from playwright.sync_api import Route, sync_playwright

from veridra import agency_prospect_discovery_web as web
from veridra.agency_market_study import market_detail
from veridra.market_intelligence import plan


def test_market_select_all_and_workflow_in_real_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    study = plan("Galway", "IE", ("dentist", "solicitor", "accountant"))
    monkeypatch.setattr(web, "_market_study", lambda _request, _id: study)
    request = Request({"type": "http", "method": "GET", "path": "/test", "headers": []})
    script = bytes(web.market_selection_script(study.study_id, request).body).decode("utf-8")
    page_html = market_detail(study)
    url = "https://veridra.test/agency/prospects/discover/market/" + study.study_id
    posted = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            def route_handler(route: Route) -> None:
                if route.request.url.endswith("/selection.js"):
                    route.fulfill(status=200, content_type="application/javascript", body=script)
                elif route.request.url.endswith("/manage"):
                    posted.append(parse_qs(route.request.post_data or ""))
                    route.fulfill(status=200, content_type="text/plain", body="OK")
                elif route.request.url.endswith("/map-view"):
                    route.fulfill(status=200, content_type="text/html", body="<html><body>map</body></html>")
                else:
                    route.fulfill(status=200, content_type="text/html", body=page_html, headers={
                        "content-security-policy": "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-src 'self'; form-action 'self'"
                    })
            page.route("https://veridra.test/**", route_handler)
            page.goto(url)
            boxes = page.locator("input[form='market-bulk'][name='sector']")
            assert boxes.count() == 3
            page.locator("#market-select-all").check()
            assert all(boxes.nth(i).is_checked() for i in range(3))
            page.locator("#market-select-all").uncheck()
            assert not any(boxes.nth(i).is_checked() for i in range(3))
            boxes.nth(1).check()
            assert page.locator("#market-select-all").evaluate("(element) => element.indeterminate")
            page.get_by_role("button", name="Run Selected").click()
            assert posted[-1]["sector"] == ["solicitor"]
            assert posted[-1]["action"] == ["queue"]
            page.goto(url)
            page.get_by_role("button", name="Edit", exact=True).click()
            assert page.locator("#market-tab-edit").is_checked()
            assert page.locator(".market-bottom").get_attribute("open") is not None
            page.goto(url)
            page.get_by_role("button", name="Run All").click()
            assert posted[-1]["action"] == ["queue_all"]
            page.goto(url)
            page.locator("#market-select-all").check()
            page.once("dialog", lambda dialog: dialog.dismiss())
            page.get_by_role("button", name="Delete Selected").click()
            assert len(posted) == 2
            page.once("dialog", lambda dialog: dialog.accept())
            page.get_by_role("button", name="Delete Selected").click()
            assert posted[-1]["action"] == ["remove"]
            assert len(posted[-1]["sector"]) == 3
        finally:
            browser.close()
