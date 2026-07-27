from __future__ import annotations

import zipfile
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

from fastapi import Request
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from veridra import crawl_profile_web
from veridra.core import Assessment, demo_assessment
from veridra.crawl_profiles import CrawlProfile, CrawlProfileName
from veridra.project_store import ClientProject, ProjectStore
from veridra.runtime import app


def _capture_assessment(
    captured: list[CrawlProfile],
) -> Callable[[str, CrawlProfile, Request], Assessment]:
    def fake(url: str, profile: CrawlProfile, request: Request) -> Assessment:
        del url, request
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

    excessive_bytes = client.get(
        "/crawl/assess",
        params={
            "url": "https://example.com",
            "crawl_profile": "custom",
            "max_total_bytes": 30_000_001,
        },
    )
    assert excessive_bytes.status_code == 400


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


def test_complete_custom_profile_is_applied_to_operator_route(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: list[CrawlProfile] = []
    monkeypatch.setattr(
        crawl_profile_web,
        "_assessment",
        _capture_assessment(captured),
    )
    parameters = {
        "url": "https://example.com",
        "crawl_profile": "custom",
        "max_pages": 35,
        "max_depth": 2,
        "max_total_bytes": 7_000_000,
        "per_page_bytes": 550_000,
        "timeout": 6.5,
        "max_sitemaps": 6,
        "max_sitemap_urls": 160,
    }
    response = TestClient(app).get("/crawl/assess", params=parameters)
    assert response.status_code == 200

    limits = captured[0].limits
    assert limits.max_pages == 35
    assert limits.max_depth == 2
    assert limits.max_total_bytes == 7_000_000
    assert limits.per_page_bytes == 550_000
    assert limits.timeout == 6.5
    assert limits.max_sitemaps == 6
    assert limits.max_sitemap_urls == 160


def test_saved_project_uses_its_complete_custom_crawl_profile(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))
    project = ClientProject.build(
        name="Custom client",
        target_url="https://example.com",
        crawl_profile="custom",
        crawl_max_pages=45,
        crawl_max_depth=2,
        crawl_max_total_bytes=9_000_000,
        crawl_per_page_bytes=650_000,
        crawl_timeout=8.5,
        crawl_max_sitemaps=8,
        crawl_max_sitemap_urls=220,
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
    limits = captured[0].limits
    assert limits.max_pages == 45
    assert limits.max_depth == 2
    assert limits.max_total_bytes == 9_000_000
    assert limits.per_page_bytes == 650_000
    assert limits.timeout == 8.5
    assert limits.max_sitemaps == 8
    assert limits.max_sitemap_urls == 220


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
    parameters = {
        "url": "https://example.com",
        "crawl_profile": "custom",
        "max_pages": 20,
        "max_depth": 2,
        "max_total_bytes": 6_000_000,
        "per_page_bytes": 500_000,
        "timeout": 6.0,
        "max_sitemaps": 5,
        "max_sitemap_urls": 140,
    }

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
    assert captured[0].limits == captured[1].limits
