from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from veridra import agency_prospect_discovery_web as views
from veridra.market_intelligence import add_observations, plan
from veridra.prospect_discovery import ObservedBusiness


def test_city_map_http_routes_are_accessible_without_asterisk_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    study = plan("Galway", "IE", ("dentist",))
    result = ObservedBusiness.model_validate({
        "provider": "google_maps",
        "provider_key": "google-maps:example",
        "name": "Sample Galway Clinic",
        "category": "Dentist",
        "locality": "Galway",
        "country_code": "IE",
        "source_url": "https://www.google.com/maps/place/example/!3d53.2707!4d-9.0568",
    })
    study = add_observations(study, "dentist", [result])
    monkeypatch.setattr(views, "_market_study", lambda _request, _id: study)

    app = FastAPI()
    app.include_router(views.router)
    client = TestClient(app)
    url = f"/agency/prospects/discover/market/{study.study_id}"

    embed = views.geographic_overview(study) if hasattr(views, "geographic_overview") else ""
    assert "/map-view" in embed or "/map-view" in __import__(
        "veridra.agency_market_study", fromlist=["geographic_overview"]
    ).geographic_overview(study)

    page = client.get(url + "/map-view")
    assert page.status_code == 200, page.text
    assert "text/html" in page.headers["content-type"]
    assert "leaflet" in page.text.lower()
    assert "/map-script" in page.text

    script = client.get(url + "/map-script")
    assert script.status_code == 200, script.text
    assert "Sample Galway Clinic" in script.text
    assert "application/javascript" in script.headers["content-type"]

    assert client.get(url + "/map-view**").status_code == 404
