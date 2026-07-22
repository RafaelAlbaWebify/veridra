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


def test_project_persists_named_and_custom_profiles() -> None:
    standard = ClientProject.build(
        name="Client",
        target_url="example.com",
        crawl_profile="standard",
    )
    assert standard.crawl_profile == CrawlProfileName.standard
    assert standard.resolved_crawl_profile().limits.max_pages == 25

    custom = ClientProject.build(
        name="Custom",
        target_url="example.com",
        crawl_profile="custom",
        crawl_max_pages=30,
        crawl_max_depth=2,
    )
    assert custom.crawl_max_pages == 30
    assert custom.resolved_crawl_profile().limits.max_depth == 2
