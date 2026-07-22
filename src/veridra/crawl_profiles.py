from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum

from .crawl import CrawlLimits


class CrawlProfileName(StrEnum):
    quick = "quick"
    standard = "standard"
    deep = "deep"
    custom = "custom"


@dataclass(frozen=True)
class CrawlProfile:
    name: CrawlProfileName
    limits: CrawlLimits

    def evidence(self) -> dict[str, object]:
        return {"profile": self.name.value, "effective_limits": asdict(self.limits)}


_PROFILES = {
    CrawlProfileName.quick: CrawlLimits(max_pages=10, max_depth=1),
    CrawlProfileName.standard: CrawlLimits(
        max_pages=25,
        max_depth=2,
        max_total_bytes=10_000_000,
        max_sitemaps=8,
        max_sitemap_urls=250,
    ),
    CrawlProfileName.deep: CrawlLimits(
        max_pages=100,
        max_depth=3,
        max_total_bytes=30_000_000,
        max_sitemaps=15,
        max_sitemap_urls=1_000,
    ),
}

_HARD_CAPS = CrawlLimits(
    max_pages=100,
    max_depth=3,
    max_total_bytes=30_000_000,
    per_page_bytes=1_000_000,
    timeout=12.0,
    max_sitemaps=15,
    max_sitemap_urls=1_000,
)


def resolve_crawl_profile(
    name: str | CrawlProfileName = CrawlProfileName.quick,
    *,
    max_pages: int | None = None,
    max_depth: int | None = None,
    max_total_bytes: int | None = None,
    per_page_bytes: int | None = None,
    timeout: float | None = None,
    max_sitemaps: int | None = None,
    max_sitemap_urls: int | None = None,
) -> CrawlProfile:
    try:
        profile_name = CrawlProfileName(name)
    except ValueError as exc:
        raise ValueError("Unknown crawl profile.") from exc

    if profile_name != CrawlProfileName.custom:
        supplied = (
            max_pages,
            max_depth,
            max_total_bytes,
            per_page_bytes,
            timeout,
            max_sitemaps,
            max_sitemap_urls,
        )
        if any(value is not None for value in supplied):
            raise ValueError("Custom crawl values require the custom profile.")
        return CrawlProfile(profile_name, _PROFILES[profile_name])

    values = CrawlLimits(
        max_pages=max_pages if max_pages is not None else 10,
        max_depth=max_depth if max_depth is not None else 1,
        max_total_bytes=(
            max_total_bytes if max_total_bytes is not None else 5_000_000
        ),
        per_page_bytes=(per_page_bytes if per_page_bytes is not None else 750_000),
        timeout=timeout if timeout is not None else 8.0,
        max_sitemaps=max_sitemaps if max_sitemaps is not None else 5,
        max_sitemap_urls=(
            max_sitemap_urls if max_sitemap_urls is not None else 100
        ),
    )
    if not 1 <= values.max_pages <= _HARD_CAPS.max_pages:
        raise ValueError("Custom max_pages is outside the allowed range.")
    if not 0 <= values.max_depth <= _HARD_CAPS.max_depth:
        raise ValueError("Custom max_depth is outside the allowed range.")
    if not 1 <= values.max_total_bytes <= _HARD_CAPS.max_total_bytes:
        raise ValueError("Custom max_total_bytes is outside the allowed range.")
    if not 1 <= values.per_page_bytes <= _HARD_CAPS.per_page_bytes:
        raise ValueError("Custom per_page_bytes is outside the allowed range.")
    if not 0.5 <= values.timeout <= _HARD_CAPS.timeout:
        raise ValueError("Custom timeout is outside the allowed range.")
    if not 0 <= values.max_sitemaps <= _HARD_CAPS.max_sitemaps:
        raise ValueError("Custom max_sitemaps is outside the allowed range.")
    if not 0 <= values.max_sitemap_urls <= _HARD_CAPS.max_sitemap_urls:
        raise ValueError("Custom max_sitemap_urls is outside the allowed range.")
    return CrawlProfile(profile_name, values)


def anonymous_crawl_profile() -> CrawlProfile:
    return resolve_crawl_profile(CrawlProfileName.quick)
