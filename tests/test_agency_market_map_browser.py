"""Browser regression for the actual City Market Study iframe under security headers."""
from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from playwright.sync_api import Route, expect, sync_playwright

from veridra import agency_prospect_discovery_web as views
from veridra.agency_market_study import geographic_overview
from veridra.market_intelligence import CityStudy, add_observations, plan
from veridra.prospect_discovery import ObservedBusiness
from veridra.runtime_config import RuntimeEnvironment
from veridra.security_headers import SecurityHeadersMiddleware


@contextmanager
def _server(study: CityStudy) -> Iterator[str]:
    app = FastAPI()
    base = f"/agency/prospects/discover/market/{study.study_id}"

    @app.get(base, response_class=HTMLResponse)
    def parent() -> str:
        return geographic_overview(study)

    app.include_router(views.router)
    app.add_middleware(SecurityHeadersMiddleware, environment=RuntimeEnvironment.operator)
    original = views._market_study
    views._market_study = lambda _request, _id: study
    listening = socket.socket()
    listening.bind(("127.0.0.1", 0))
    listening.listen(128)
    port = listening.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [listening]}, daemon=True
    )
    try:
        thread.start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        assert server.started
        yield f"http://127.0.0.1:{port}{base}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listening.close()
        views._market_study = original


def test_market_street_map_renders_inside_operator_csp() -> None:
    study = plan("Galway", "IE", ("dentist",))
    observation = ObservedBusiness.model_validate({
        "provider": "google_maps",
        "provider_key": "google-maps:galway",
        "name": "Test Galway Dental",
        "category": "Dentist",
        "locality": "Galway",
        "country_code": "IE",
        "source_url": "https://www.google.com/maps/place/example/!3d53.2707!4d-9.0568",
    })
    study = add_observations(study, "dentist", [observation])
    fake_leaflet = """
      window.L = {
        map: function() { return {fitBounds: function() {}}; },
        tileLayer: function() { return {addTo: function() {}}; },
        circleMarker: function() {
          const marker = document.createElement('span');
          marker.dataset.testMarker = '1';
          document.getElementById('map').appendChild(marker);
          return {
            addTo: function() { return this; },
            bindPopup: function(node) { marker.appendChild(node); }
          };
        }
      };
    """

    def mock_dependency(route: Route) -> None:
        if route.request.url.endswith(".css"):
            route.fulfill(status=200, content_type="text/css", body="")
        else:
            route.fulfill(
                status=200, content_type="application/javascript", body=fake_leaflet
            )

    with _server(study) as url:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.route("https://unpkg.com/**", mock_dependency)
                response = page.goto(url)
                assert response is not None and response.status == 200
                iframe = page.frame_locator("iframe")
                expect(iframe.locator("#map")).to_be_visible(timeout=10000)
                expect(iframe.locator("[data-test-marker]")).to_have_count(1)
                expect(iframe.get_by_text("Test Galway Dental")).to_be_visible()
            finally:
                browser.close()
