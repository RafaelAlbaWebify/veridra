# ruff: noqa: E501
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from veridra import agency_prospect_discovery_web as web
from veridra.assisted_discovery import BoundedDiscoveryLimits, TraversalObservation
from veridra.market_intelligence import plan
from veridra.prospect_discovery import ObservedBusiness


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/test", "headers": []})


def _observation() -> TraversalObservation:
    return TraversalObservation(
        business=ObservedBusiness.model_validate({
            "provider": "google_maps", "provider_key": "google-maps:galway-1",
            "name": "Galway Solicitors", "category": "Solicitor",
            "country_code": "IE", "locality": "Galway",
            "source_url": "https://www.google.com/maps/place/test",
            "observed_at": datetime(2026, 10, 9, tzinfo=UTC),
        }),
        query_text="solicitor in Galway, IE", query_sequence=1,
        result_rank=1, first_seen_scroll_step=0,
    )


def test_failed_market_capture_provides_unlock_and_does_not_replace_study(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    study = plan("Galway", "IE", ("solicitor",))
    class FailingRegistry:
        def snapshot(self, **_kwargs: Any) -> Any:
            manager = SimpleNamespace(snapshot=lambda: SimpleNamespace(query_text="solicitor in Galway, IE"))
            return SimpleNamespace(manager=manager, observations=(), limits=BoundedDiscoveryLimits())
        def collect(self, **_kwargs: Any) -> Any:
            raise RuntimeError("Browser worker stopped")
    monkeypatch.setattr(web, "_REGISTRY", FailingRegistry())
    monkeypatch.setattr(web, "_identity", lambda _request: SimpleNamespace(tenant_id="tenant"))
    monkeypatch.setattr(web, "_trusted_origin", lambda _request: None)
    monkeypatch.setattr(web, "_root", lambda _request: tmp_path)
    monkeypatch.setattr(web, "all_studies", lambda *_args: [study])
    response = asyncio.run(web.collect_into_market("session-1", _request()))
    assert isinstance(response, HTMLResponse)
    assert response.status_code == 409
    assert b"Discard this session and unlock Discovery" in response.body
    assert b"Browser worker stopped" in response.body
    assert study.queries[0].status == "planned"


def test_saved_capture_can_complete_without_recollecting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    study = plan("Galway", "IE", ("solicitor",))
    completed: list[str] = []
    class SavedRegistry:
        def snapshot(self, **_kwargs: Any) -> Any:
            return SimpleNamespace(manager=None, observations=(_observation(),), limits=BoundedDiscoveryLimits())
        def collect(self, **_kwargs: Any) -> Any:
            raise AssertionError("Must not recollect already saved observations")
        def finish(self, **_kwargs: Any) -> None:
            completed.append("finished")
    monkeypatch.setattr(web, "_REGISTRY", SavedRegistry())
    monkeypatch.setattr(web, "_identity", lambda _request: SimpleNamespace(tenant_id="tenant"))
    monkeypatch.setattr(web, "_trusted_origin", lambda _request: None)
    monkeypatch.setattr(web, "_root", lambda _request: tmp_path)
    monkeypatch.setattr(web, "all_studies", lambda *_args: [study])
    response = asyncio.run(web.collect_into_market("session-1", _request()))
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303
    assert completed == ["finished"]
    assert list(tmp_path.rglob("*.json")), "Market study must be persisted before finish"
