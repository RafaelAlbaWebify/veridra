from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import Page, sync_playwright

OUTPUT = Path("artifacts/browser")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_ready(url: str, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{url}/health", timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("Veridra did not become ready for browser auditing.")


def _keyboard_contract(page: Page) -> bool:
    page.locator("body").click(position={"x": 1, "y": 1})
    input_reached = False
    for _ in range(12):
        page.keyboard.press("Tab")
        if page.evaluate("document.activeElement && document.activeElement.id") == "url":
            input_reached = True
            break
    if not input_reached:
        return False
    page.keyboard.press("Tab")
    if page.evaluate("document.activeElement && document.activeElement.id") != "profile":
        return False
    page.keyboard.press("Tab")
    return page.evaluate(
        "document.activeElement && document.activeElement.textContent.trim()"
    ) == "Run assessment"


def _public_keyboard_contract(page: Page) -> bool:
    page.locator("body").click(position={"x": 1, "y": 1})
    input_reached = False
    for _ in range(10):
        page.keyboard.press("Tab")
        if page.evaluate("document.activeElement && document.activeElement.id") == "free-url":
            input_reached = True
            break
    if not input_reached:
        return False
    page.keyboard.press("Tab")
    return page.evaluate(
        "document.activeElement && document.activeElement.textContent.trim()"
    ) == "Analyse website"


def _check_viewport(page: Page, name: str, width: int, height: int) -> dict[str, bool]:
    page.set_viewport_size({"width": width, "height": height})
    page.goto(page.url, wait_until="networkidle")
    checks = {
        "single_main_heading": page.locator("main h2").count() == 1,
        "navigation_landmark": page.locator("nav").count() == 1,
        "labelled_url_input": page.get_by_label("Public website").count() == 1,
        "labelled_profile_selector": page.get_by_label("Report profile").count() == 1,
        "primary_action": page.get_by_role("button", name="Run assessment").count() == 1,
        "report_action": page.get_by_role("link", name="Open report").count() == 1,
        "no_horizontal_overflow": bool(
            page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        ),
        "keyboard_navigation": _keyboard_contract(page),
    }
    page.screenshot(path=OUTPUT / f"dashboard-{name}.png", full_page=True)
    return checks


def _check_public_viewport(
    page: Page,
    base_url: str,
    name: str,
    width: int,
    height: int,
) -> dict[str, bool]:
    page.set_viewport_size({"width": width, "height": height})
    page.goto(f"{base_url}/free", wait_until="networkidle")
    checks = {
        "single_main_heading": page.locator("main h1").count() == 1,
        "labelled_url_input": page.get_by_label("Public website").count() == 1,
        "primary_action": page.get_by_role("button", name="Analyse website").count() == 1,
        "tool_cards": page.locator("article.card").count() == 5,
        "no_operator_links": page.locator("a[href='/projects'], a[href='/profiles'], a[href='/history']").count() == 0,
        "no_horizontal_overflow": bool(
            page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        ),
        "keyboard_navigation": _public_keyboard_contract(page),
    }
    page.screenshot(path=OUTPUT / f"free-tools-{name}.png", full_page=True)
    return checks


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "veridra.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    report: dict[str, object] = {"passed": False, "checks": {}}
    try:
        _wait_until_ready(base_url)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            page.goto(base_url, wait_until="networkidle")
            checks = {
                "desktop": _check_viewport(page, "desktop", 1440, 1000),
                "mobile": _check_viewport(page, "mobile", 390, 844),
                "free_desktop": _check_public_viewport(
                    page, base_url, "desktop", 1440, 1000
                ),
                "free_mobile": _check_public_viewport(
                    page, base_url, "mobile", 390, 844
                ),
            }
            browser.close()
        passed = all(all(values.values()) for values in checks.values())
        report = {"passed": passed, "checks": checks}
    except Exception as exc:
        report = {"passed": False, "checks": {}, "error": str(exc)}
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        (OUTPUT / "browser-audit.json").write_text(
            json.dumps(report, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
