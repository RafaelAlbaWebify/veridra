# ruff: noqa: E501
"""Real Chromium regression: CSP and every sector toolbar control."""
from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qs

import pytest
from fastapi import Request
from playwright.sync_api import Route, sync_playwright

from veridra import agency_prospect_discovery_web as web
from veridra.agency_market_study import market_detail
from veridra.market_intelligence import add_observations, plan
from veridra.prospect_discovery import ObservedBusiness


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


def test_market_candidate_filters_in_chromium(monkeypatch: pytest.MonkeyPatch) -> None:
    study = plan("Galway", "IE", ("dentist", "estate agent"))
    def candidate(name: str, key: str, *, category: str, website: str | None = None) -> ObservedBusiness:
        return ObservedBusiness.model_validate(dict(
            provider="google_maps", provider_key=key, name=name,
            category=category, locality="Galway", country_code="IE",
            website=website, source_url="https://maps.google.com/",
            observed_at=datetime(2026, 10, 9, tzinfo=UTC),
        ))
    study = add_observations(study, "dentist", [
        candidate("Aster Dental", "d1", category="Dentist"),
        candidate("Briar Dental", "d2", category="Dentist", website="https://briar.example"),
    ])
    study = add_observations(study, "estate agent", [
        candidate("Cedar Property", "e1", category="Estate agency"),
    ])
    monkeypatch.setattr(web, "_market_study", lambda _req, _id: study)
    request = Request({"type": "http", "method": "GET", "path": "/test", "headers": []})
    script = bytes(web.market_selection_script(study.study_id, request).body).decode("utf-8")
    page_html = market_detail(study)
    url = "https://veridra.test/agency/prospects/discover/market/" + study.study_id
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            def route_handler(route: Route) -> None:
                if route.request.url.endswith("/selection.js"):
                    route.fulfill(status=200, content_type="application/javascript", body=script)
                elif route.request.url.endswith("/map-view"):
                    route.fulfill(status=200, content_type="text/html", body="<html>map</html>")
                else:
                    route.fulfill(status=200, content_type="text/html", body=page_html, headers={
                        "content-security-policy": "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-src 'self'"
                    })
            page.route("https://veridra.test/**", route_handler)
            page.goto(url)
            page.locator(".market-bottom summary").click()
            rows = page.locator(".market-business-row:visible")
            assert rows.count() == 3
            page.locator("#market-business-sector").select_option("estate agent")
            assert rows.count() == 1
            assert "Cedar Property" in rows.first.inner_text()
            page.locator("#market-business-sector").select_option("")
            page.locator("#market-business-website").select_option("yes")
            assert rows.count() == 1
            assert "Briar Dental" in rows.first.inner_text()
            page.locator("#market-business-search").fill("aster")
            assert rows.count() == 0
            assert "0 of 3" in page.locator("#market-business-count").inner_text()
            page.get_by_role("button", name="Reset filters").click()
            assert rows.count() == 3
        finally:
            browser.close()


def test_market_shortlist_selection_respects_filters_in_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study = plan("Galway", "IE", ("dentist", "estate agent"))
    def business(name: str, key: str) -> ObservedBusiness:
        return ObservedBusiness.model_validate({
            "provider": "google_maps", "provider_key": key, "name": name,
            "locality": "Galway", "country_code": "IE",
            "observed_at": datetime(2026, 10, 9, tzinfo=UTC),
        })
    study = add_observations(study, "dentist", [
        business("Aster Dental", "a"), business("Briar Dental", "b"),
    ])
    study = add_observations(study, "estate agent", [business("Cedar Property", "c")])
    monkeypatch.setattr(web, "_market_study", lambda _req, _id: study)
    request = Request({"type": "http", "method": "GET", "path": "/test", "headers": []})
    script = bytes(web.market_selection_script(study.study_id, request).body).decode("utf-8")
    url = "https://veridra.test/agency/prospects/discover/market/" + study.study_id
    posted: list[dict[str, list[str]]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            def route_handler(route: Route) -> None:
                if route.request.url.endswith("/selection.js"):
                    route.fulfill(status=200, content_type="application/javascript", body=script)
                elif route.request.url.endswith("/shortlist"):
                    posted.append(parse_qs(route.request.post_data or ""))
                    route.fulfill(status=200, content_type="text/plain", body="saved")
                elif route.request.url.endswith("/map-view"):
                    route.fulfill(status=200, content_type="text/html", body="<html>map</html>")
                else:
                    route.fulfill(status=200, content_type="text/html", body=market_detail(study), headers={
                        "content-security-policy": "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-src 'self'; form-action 'self'"
                    })
            page.route("https://veridra.test/**", route_handler)
            page.goto(url)
            page.locator(".market-bottom summary").click()
            checks = page.locator(".market-business-row input[name='business_id'][form='market-shortlist-form']")
            assert checks.count() == 3
            page.locator("#market-business-sector").select_option("dentist")
            page.locator("#market-select-businesses").check()
            assert sum(checks.nth(i).is_checked() for i in range(3)) == 2
            page.locator("#market-business-search").fill("Aster")
            assert sum(checks.nth(i).is_checked() for i in range(3)) == 1
            page.get_by_role("button", name="Shortlist selected").click()
            assert len(posted) == 1
            assert posted[0]["action"] == ["shortlist"]
            assert len(posted[0]["business_id"]) == 1
        finally:
            browser.close()
