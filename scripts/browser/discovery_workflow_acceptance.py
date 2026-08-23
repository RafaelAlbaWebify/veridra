from __future__ import annotations

import json
import os
import socket
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_http(url: str, timeout: float = 20.0) -> None:
    import urllib.request

    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:  # noqa: S310
                if response.status < 500:
                    return
        except Exception as exc:  # pragma: no cover - diagnostic path
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"Temporary Veridra server did not become ready: {last_error}")


@dataclass(slots=True)
class _FakeBatch:
    tenant_id: str
    manager: Any
    limits: Any
    observations: tuple[Any, ...] = ()


class _FixtureProvider:
    def __init__(self) -> None:
        self.launched = False

    def launch(self, *, start_url: str) -> None:
        if not start_url:
            raise ValueError("start_url is required")
        self.launched = True

    def collect_bounded(self, *, query_text: str, query_sequence: int, limits: Any) -> Any:
        from veridra.assisted_discovery import (
            TraversalObservation,
            TraversalProgress,
            TraversalResult,
            TraversalStopReason,
        )
        from veridra.prospect_discovery import ObservedBusiness

        now = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)
        records = (
            ("Acceptance Dental One", "Dentist", "https://acceptance-one.example/"),
            ("Acceptance Dental Two", "Acceptance Dental Two", "https://acceptance-two.example/"),
            ("Sponsored Acceptance", "Sponsored", None),
        )
        observations: list[TraversalObservation] = []
        for rank, (name, category, website) in enumerate(records, start=1):
            business = ObservedBusiness.model_validate(
                {
                    "provider": "google_maps",
                    "provider_key": f"acceptance:{rank}",
                    "name": name,
                    "category": category,
                    "locality": "Vigo",
                    "administrative_area": "Pontevedra",
                    "country_code": "ES",
                    "website": website,
                    "source_url": f"https://www.google.com/maps/place/acceptance-{rank}",
                    "observed_at": now,
                }
            )
            observations.append(
                TraversalObservation(
                    business=business,
                    query_text=query_text,
                    query_sequence=query_sequence,
                    result_rank=rank,
                    first_seen_scroll_step=0,
                )
            )
        bounded = tuple(observations[: limits.max_results])
        return TraversalResult(
            observations=bounded,
            progress=TraversalProgress(
                query_text=query_text,
                query_sequence=query_sequence,
                scroll_step=0,
                unique_results=len(bounded),
                stagnant_scrolls=0,
                elapsed_seconds=0.01,
                stop_reason=TraversalStopReason.max_results
                if len(bounded) >= limits.max_results
                else TraversalStopReason.end_of_list,
            ),
        )

    def stop(self) -> None:
        return None


class _FixtureRegistry:
    def __init__(self) -> None:
        self._batch: _FakeBatch | None = None

    def start(
        self,
        *,
        tenant_id: str,
        query_text: str,
        country_code: str,
        locality: str,
        administrative_area: str,
        limits: Any,
    ) -> str:
        del country_code, locality, administrative_area
        from veridra.assisted_discovery import AssistedDiscoveryManager
        from veridra.assisted_discovery_acceptance_cli import build_start_url

        if self._batch is not None:
            raise ValueError("Another acceptance discovery is active.")
        manager = AssistedDiscoveryManager(_FixtureProvider())
        session = manager.launch(
            query_text=query_text,
            query_sequence=1,
            start_url=build_start_url(query_text),
        )
        if session.session_id is None:
            raise RuntimeError("Acceptance session did not receive an id.")
        self._batch = _FakeBatch(tenant_id=tenant_id, manager=manager, limits=limits)
        return session.session_id

    def _require(self, tenant_id: str, session_id: str) -> _FakeBatch:
        if self._batch is None or self._batch.tenant_id != tenant_id:
            raise ValueError("Discovery review was not found.")
        if self._batch.manager.snapshot().session_id != session_id:
            raise ValueError("Discovery review was not found.")
        return self._batch

    def snapshot(self, *, tenant_id: str, session_id: str) -> _FakeBatch:
        return self._require(tenant_id, session_id)

    def collect(self, *, tenant_id: str, session_id: str) -> _FakeBatch:
        batch = self._require(tenant_id, session_id)
        batch.manager.mark_ready(session_id)
        session = batch.manager.collect(session_id, limits=batch.limits)
        batch.observations = session.observations
        batch.manager.stop(session_id)
        return batch

    def finish(self, *, tenant_id: str, session_id: str) -> None:
        batch = self._require(tenant_id, session_id)
        batch.manager.stop(session_id)
        self._batch = None


def _shot(page: Page, evidence: Path, name: str) -> None:
    page.screenshot(path=str(evidence / f"{name}.png"), full_page=True)


def _assert_text(page: Page, text: str) -> None:
    page.get_by_text(text, exact=False).first.wait_for(state="visible", timeout=5000)


def main() -> int:
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    downloads = Path.home() / "Downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = downloads / f"VERIDRA_BROWSER_ACCEPTANCE_{stamp}.zip"

    with tempfile.TemporaryDirectory(prefix="veridra-browser-acceptance-") as temporary:
        temp = Path(temporary)
        evidence = temp / "evidence"
        evidence.mkdir()
        identity_db = temp / "identity" / "veridra.sqlite3"
        tenant_root = temp / "tenants"
        identity_db.parent.mkdir(parents=True)
        tenant_root.mkdir(parents=True)

        os.environ.update(
            {
                "VERIDRA_ENV": "development",
                "VERIDRA_BIND_HOST": "127.0.0.1",
                "VERIDRA_BIND_PORT": str(port),
                "VERIDRA_ALLOWED_HOSTS": "127.0.0.1,localhost",
                "VERIDRA_TRUSTED_ORIGIN": base_url,
                "VERIDRA_IDENTITY_DB": str(identity_db),
                "VERIDRA_TENANT_DATA_ROOT": str(tenant_root),
            }
        )

        import uvicorn

        from veridra import agency_prospect_discovery_web
        from veridra.runtime import app

        agency_prospect_discovery_web._REGISTRY = _FixtureRegistry()  # type: ignore[assignment]

        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        _wait_http(base_url + "/")

        report: dict[str, Any] = {
            "started_at": datetime.now(UTC).isoformat(),
            "base_url": base_url,
            "steps": [],
            "status": "running",
        }

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 1000})

                page.goto(base_url + "/onboarding", wait_until="networkidle")
                page.get_by_label("Agency or organisation name").fill("Webify Acceptance")
                page.get_by_label("Workspace slug").fill("webify-acceptance")
                page.get_by_label("Your name").fill("Acceptance Operator")
                page.get_by_label("Email").fill("acceptance@example.test")
                page.get_by_label("Password", exact=True).fill("AcceptancePass123!")
                page.get_by_label("Repeat password").fill("AcceptancePass123!")
                page.get_by_role("button", name="Create agency workspace").click()
                page.wait_for_url("**/agency")
                _assert_text(page, "Webify prospects")
                _shot(page, evidence, "01-agency-home")
                report["steps"].append("onboarding_and_authenticated_agency_home")

                page.goto(base_url + "/agency/prospects", wait_until="networkidle")
                _assert_text(page, "Discover prospects")
                _shot(page, evidence, "02-prospect-workbench")
                report["steps"].append("prospect_workbench_exposes_discovery_navigation")

                page.get_by_role("link", name="Discover prospects").click()
                page.wait_for_url("**/agency/prospects/discover")
                _assert_text(page, "Open discovery browser")
                _shot(page, evidence, "03-discovery-form")
                report["steps"].append("discovery_route_reachable_from_workbench")

                page.get_by_label("Search query").fill("dentist in Vigo, ES")
                page.get_by_label("Maximum results").fill("3")
                page.get_by_role("button", name="Open discovery browser").click()
                _assert_text(page, "Browser opened")
                _shot(page, evidence, "04-discovery-waiting")
                report["steps"].append("discovery_session_started")

                page.get_by_role("button", name="Collect visible results").click()
                _assert_text(page, "Review discovered businesses")
                _assert_text(page, "Acceptance Dental One")
                _assert_text(page, "Acceptance Dental Two")
                _assert_text(page, "Sponsored Acceptance")
                _assert_text(page, "No website")
                _shot(page, evidence, "05-review")
                report["steps"].append("bounded_results_presented_for_review")

                checkboxes = page.locator("input[name='selected_rank']")
                if checkboxes.count() != 2:
                    count = checkboxes.count()
                    raise AssertionError(
                        f"Expected exactly two selectable website prospects, got {count}."
                    )
                checkboxes.nth(0).check()
                checkboxes.nth(1).check()
                page.get_by_role("button", name="Ingest selected prospects").click()
                page.wait_for_url("**/agency/prospects**")
                _assert_text(page, "Acceptance Dental One")
                _assert_text(page, "Acceptance Dental Two")
                if page.get_by_text("Sponsored Acceptance", exact=False).count() != 0:
                    raise AssertionError(
                        "No-website sponsored observation was incorrectly ingested."
                    )
                _shot(page, evidence, "06-ingested-workbench")
                report["steps"].append("explicit_selection_safely_ingested_into_workbench")

                browser.close()

            report["status"] = "passed"
            return_code = 0
        except Exception as exc:
            report["status"] = "failed"
            report["error"] = f"{type(exc).__name__}: {exc}"
            return_code = 1
        finally:
            report["finished_at"] = datetime.now(UTC).isoformat()
            (evidence / "report.json").write_text(
                json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            server.should_exit = True
            thread.join(timeout=10)
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(evidence.iterdir()):
                    archive.write(path, arcname=path.name)

        print(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"Evidence ZIP: {zip_path}")
        return return_code


if __name__ == "__main__":
    raise SystemExit(main())
