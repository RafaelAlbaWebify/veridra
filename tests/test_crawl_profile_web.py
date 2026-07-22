from __future__ import annotations

import zipfile
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from veridra import crawl_profile_web
from veridra.core import Assessment, demo_assessment
from veridra.crawl_profiles import CrawlProfile, CrawlProfileName
from veridra.project_store import ClientProject, ProjectStore
from veridra.runtime import app


def _capture_assessment(
    captured: list[CrawlProfile],
) -> Callable[[str, CrawlProfile], Assessment]:
    def fake(url: str, profile: CrawlProfile) -> Assessment:
        captured.append(profile)
        return demo_assessment()

    return fake


def test_unknown_and_out_of_range_profiles_fail_before_collection() -> None:
    client = TestClient(app)
    unknown = client.get(
        "/crawl/assess",
        params={"url": "https://example.com", "crawl_profile": "unknown"},
    )
    assert unknown.status_code == 400

    too_large = client.get(
        "/crawl/assess",
        params={
            "url": "https://example.com",
            "crawl_profile": "custom",
            "max_pages": 101,
            "max_depth": 1,
        },
    )
    assert too_large.status_code == 400


def test_named_profile_is_applied_to_operator_route(monkeypatch: MonkeyPatch) -> None:
    captured: list[CrawlProfile] = []
    monkeypatch.setattr(
        crawl_profile_web,
        "_assessment",
        _capture_assessment(captured),
    )
    response = TestClient(app).get(
        "/crawl/assess",
        params={"url": "https://example.com", "crawl_profile": "standard"},
    )
    assert response.status_code == 200
    assert captured[0].name == CrawlProfileName.standard
    assert captured[0].limits.max_pages == 25
    assert captured[0].limits.max_depth == 2


def test_saved_project_uses_its_crawl_profile(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))
    project = ClientProject.build(
        name="Deep client",
        target_url="https://example.com",
        crawl_profile="deep",
    )
    entry_id = ProjectStore().save(project)
    captured: list[CrawlProfile] = []
    monkeypatch.setattr(
        crawl_profile_web,
        "_assessment",
        _capture_assessment(captured),
    )

    response = TestClient(app).get(f"/crawl/projects/{entry_id}/assess")
    assert response.status_code == 200
    assert captured[0].name == CrawlProfileName.deep
    assert captured[0].limits.max_pages == 100


def test_profile_report_and_export_routes_share_assessment(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: list[CrawlProfile] = []
    monkeypatch.setattr(
        crawl_profile_web,
        "_assessment",
        _capture_assessment(captured),
    )
    client = TestClient(app)
    parameters = {"url": "https://example.com", "crawl_profile": "quick"}

    report = client.get("/crawl/report", params=parameters)
    assert report.status_code == 200
    assert "assessment report" in report.text

    exported = client.get("/crawl/export", params=parameters)
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(BytesIO(exported.content)) as archive:
        assert set(archive.namelist()) == {
            "assessment.json",
            "manifest.sha256",
            "report.html",
        }
    assert len(captured) == 2
