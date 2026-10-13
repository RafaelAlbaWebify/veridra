# ruff: noqa: E501
"""Authenticated loopback HTTP/Chromium Market Study smoke test.

Uses only locally configured auto-login. Never submits business forms, sends
outreach, or changes Market Study records. A /login GET may create a session.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Route, sync_playwright


def evidence_result(business_count: int) -> dict[str, str | int]:
    return {"result": "PASS", "business_count": business_count, "mode": "authenticated loopback read-only", "map_tiles": "not tested: external resources blocked"}


def evidence_zip_path(output_dir: Path) -> Path:
    return output_dir / "VERIDRA_MARKET_VISUAL_EVIDENCE.zip"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--expected-count", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path.home() / "Downloads")
    args = parser.parse_args()
    parsed = urlparse(args.base_url)
    if parsed.scheme != "http" or not parsed.hostname or not ipaddress.ip_address(parsed.hostname).is_loopback or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SystemExit("FAIL: only plain HTTP loopback URLs are allowed")
    base = args.base_url.rstrip("/")
    if args.expected_count < 1:
        raise SystemExit("FAIL: expected count must be positive")
    output = Path("artifacts/market-live-readonly")
    output.mkdir(parents=True, exist_ok=True)
    screenshots: list[Path] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=False)
            page = context.new_page()
            # Only this loopback origin, only safe GET/HEAD requests. Block external assets.
            def guard(route: Route) -> None:
                url = urlparse(route.request.url)
                if route.request.method not in {"GET", "HEAD"} or url.scheme != parsed.scheme or url.hostname != parsed.hostname or url.port != parsed.port:
                    route.abort()
                else:
                    route.continue_()
            page.route("**/*", guard)
            page.goto(base + "/login", wait_until="domcontentloaded")
            page.goto(base + "/agency", wait_until="domcontentloaded")
            screenshots.append(output / "01-home.png")
            page.screenshot(path=str(screenshots[-1]), full_page=True)
            page.goto(base + "/agency/prospects/discover/market", wait_until="domcontentloaded")
            if "/login" in page.url or page.get_by_text("Sign in to Veridra").count():
                raise RuntimeError("Authentication required: operator local auto-login is not configured. No credentials were attempted.")
            links = page.locator("a[href^='/agency/prospects/discover/market/']")
            candidates = [link.get_attribute("href") for link in links.all()]
            candidates = [href for href in candidates if href and len(href.rstrip("/").split("/")[-1]) == 32]
            if len(candidates) != 1:
                raise AssertionError(f"Expected one saved market study in authenticated overview, found {len(candidates)}")
            screenshots.append(output / "02-market-overview.png")
            page.screenshot(path=str(screenshots[-1]), full_page=True)
            page.goto(base + candidates[0], wait_until="domcontentloaded")
            screenshots.append(output / "03-market-cockpit.png")
            page.screenshot(path=str(screenshots[-1]), full_page=True)
            page.locator("details.market-bottom > summary").click()
            screenshots.append(output / "04-businesses-all.png")
            page.screenshot(path=str(screenshots[-1]), full_page=True)
            rows = page.locator(".market-business-row:visible")
            if rows.count() != args.expected_count:
                raise AssertionError(f"Expected {args.expected_count} business rows, got {rows.count()}")
            for control in ("#market-business-prequalification", "#market-business-website", "#market-business-search"):
                if page.locator(control).count() != 1:
                    raise AssertionError("Missing interactive control: " + control)
            page.locator("#market-business-prequalification").select_option("needs-verification")
            screenshots.append(output / "05-businesses-filtered.png")
            page.screenshot(path=str(screenshots[-1]), full_page=True)
            page.get_by_role("button", name="Reset filters").click()
            if rows.count() != args.expected_count:
                raise AssertionError("Filter reset did not restore all rows")
            verified_business_count = rows.count()
            screenshots.append(output / "06-businesses-reset.png")
            page.screenshot(path=str(screenshots[-1]), full_page=True)
            for index, tab in enumerate(("coverage", "review"), start=7):
                tab_locator = page.locator(f"#market-tab-{tab}")
                if tab_locator.count() != 1:
                    raise AssertionError(f"Missing market tab: {tab}")
                page.locator(f"label[for=market-tab-{tab}]").click()
                if not tab_locator.is_checked():
                    raise AssertionError(f"Tab did not activate: {tab}")
                screenshots.append(output / f"{index:02d}-{tab}.png")
                page.screenshot(path=str(screenshots[-1]), full_page=True)
            result = evidence_result(verified_business_count)
            report = output / "result.json"
            (report).write_text(json.dumps(result, indent=2), encoding="utf-8")
            args.output_dir.mkdir(parents=True, exist_ok=True)
            archive = evidence_zip_path(args.output_dir)
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                for item in [*screenshots, report]:
                    bundle.write(item, arcname=item.name)
            print(f"EVIDENCE ZIP: {archive.resolve()}")
            print(f"PASS authenticated loopback Market Study: {verified_business_count} businesses; filters restored")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
