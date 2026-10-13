"""Capture the five core VERIDRA operator areas without modifying commercial data."""
from __future__ import annotations

import argparse
import ipaddress
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Route, sync_playwright

AREAS = (
    ("01-prospects", "/agency/prospects", "Prospects"),
    ("02-sales-proposals", "/agency/deals", "Sales / proposals"),
    ("03-customers", "/agency/customers", "Customers"),
    ("04-client-projects", "/agency/projects", "Client projects"),
    ("05-presence-care", "/agency/recurring-services", "Presence Care"),
)


def capture(base_url: str, destination: Path) -> Path:
    parsed = urlparse(base_url)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1"}
            or not ipaddress.ip_address(parsed.hostname).is_loopback
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}):
        raise ValueError("Only bare HTTP loopback URLs are permitted")
    destination.mkdir(parents=True, exist_ok=True)
    report: list[dict[str, str | int]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(viewport={"width": 1600, "height": 950},
                                          accept_downloads=False)
            page = context.new_page()

            def readonly(route: Route) -> None:
                url = urlparse(route.request.url)
                if (route.request.method not in {"GET", "HEAD"}
                        or url.scheme != parsed.scheme or url.hostname != parsed.hostname
                        or url.port != parsed.port):
                    route.abort()
                else:
                    route.continue_()

            page.route("**/*", readonly)
            for filename, path, label in AREAS:
                response = page.goto(base_url.rstrip("/") + path,
                                     wait_until="domcontentloaded", timeout=15000)
                if response is None or response.status != 200:
                    raise RuntimeError(f"{label}: HTTP {response.status if response else 'none'}")
                if "/login" in page.url or page.get_by_text("Sign in to Veridra").count():
                    raise RuntimeError(f"{label}: authentication unavailable")
                selected = page.locator("nav.agency-nav a[aria-current='page']")
                active = selected.all_text_contents()
                if label not in [name.strip() for name in active]:
                    raise AssertionError(f"{label}: active navigation is {active!r}")
                screenshot = destination / f"{filename}.png"
                page.screenshot(path=str(screenshot), full_page=True,
                                animations="disabled", timeout=30000)
                report.append({"area": label, "path": path, "http": response.status,
                               "active_nav": active[0].strip(), "image": screenshot.name})
                print(f"PASS {label}: HTTP {response.status}; full-page capture")
        finally:
            browser.close()
    manifest = destination / "result.json"
    manifest.write_text(json.dumps({
        "status": "PASS", "mode": "local authenticated GET-only",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "notes": "Screenshots may contain real prospect or customer information. Review before sharing.",
        "areas": report,
    }, indent=2), encoding="utf-8")
    zip_path = destination / "VERIDRA_OPERATOR_5_AREAS_VISUAL_EVIDENCE.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for row in report:
            archive.write(destination / str(row["image"]), arcname=str(row["image"]))
        archive.write(manifest, arcname="result.json")
    print(f"EVIDENCE ZIP: {zip_path.resolve()}")
    return zip_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--output-dir", type=Path, default=Path.home() / "Downloads")
    args = parser.parse_args()
    capture(args.base_url, args.output_dir)


if __name__ == "__main__":
    main()
