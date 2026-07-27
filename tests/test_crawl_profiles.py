from __future__ import annotations

import pytest

from veridra.crawl_profiles import (
    CrawlProfileName,
    anonymous_crawl_profile,
    resolve_crawl_profile,
)
from veridra.project_store import ClientProject


def test_named_profiles_have_expected_limits() -> None:
    assert resolve_crawl_profile("quick").limits.max_pages == 10
    assert resolve_crawl_profile("standard").limits.max_pages == 25
    deep = resolve_crawl_profile("deep")
    assert deep.limits.max_pages == 100
    assert deep.limits.max_depth == 3


def test_custom_profile_enforces_hard_caps() -> None:
    custom = resolve_crawl_profile("custom", max_pages=40, max_depth=2)
    assert custom.name == CrawlProfileName.custom
    assert custom.limits.max_pages == 40
    with pytest.raises(ValueError, match="max_pages"):
        resolve_crawl_profile("custom", max_pages=101)
    with pytest.raises(ValueError, match="max_depth"):
        resolve_crawl_profile("custom", max_depth=4)
    with pytest.raises(ValueError, match="max_total_bytes"):
        resolve_crawl_profile("custom", max_total_bytes=30_000_001)
    with pytest.raises(ValueError, match="per_page_bytes"):
        resolve_crawl_profile("custom", per_page_bytes=1_000_001)
    with pytest.raises(ValueError, match="timeout"):
        resolve_crawl_profile("custom", timeout=12.1)
    with pytest.raises(ValueError, match="max_sitemaps"):
        resolve_crawl_profile("custom", max_sitemaps=16)
    with pytest.raises(ValueError, match="max_sitemap_urls"):
        resolve_crawl_profile("custom", max_sitemap_urls=1_001)


def test_named_profile_rejects_custom_values() -> None:
    with pytest.raises(ValueError, match="require the custom profile"):
        resolve_crawl_profile("quick", max_pages=5)


def test_unknown_profile_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown crawl profile"):
        resolve_crawl_profile("unbounded")


def test_anonymous_profile_remains_conservative() -> None:
    profile = anonymous_crawl_profile()
    assert profile.name == CrawlProfileName.quick
    assert profile.limits.max_pages == 10
    assert profile.limits.max_depth == 1


def test_project_persists_named_and_complete_custom_profiles() -> None:
    standard = ClientProject.build(
        name="Client",
        target_url="example.com",
        crawl_profile="standard",
    )
    assert standard.crawl_profile == CrawlProfileName.standard
    assert standard.resolved_crawl_profile().limits.max_pages == 25
    assert standard.crawl_max_total_bytes is None

    custom = ClientProject.build(
        name="Custom",
        target_url="example.com",
        crawl_profile="custom",
        crawl_max_pages=30,
        crawl_max_depth=2,
        crawl_max_total_bytes=8_000_000,
        crawl_per_page_bytes=600_000,
        crawl_timeout=7.5,
        crawl_max_sitemaps=7,
        crawl_max_sitemap_urls=180,
    )
    assert custom.crawl_max_pages == 30
    assert custom.crawl_max_depth == 2
    assert custom.crawl_max_total_bytes == 8_000_000
    assert custom.crawl_per_page_bytes == 600_000
    assert custom.crawl_timeout == 7.5
    assert custom.crawl_max_sitemaps == 7
    assert custom.crawl_max_sitemap_urls == 180

    resolved = custom.resolved_crawl_profile().limits
    assert resolved.max_pages == 30
    assert resolved.max_depth == 2
    assert resolved.max_total_bytes == 8_000_000
    assert resolved.per_page_bytes == 600_000
    assert resolved.timeout == 7.5
    assert resolved.max_sitemaps == 7
    assert resolved.max_sitemap_urls == 180
