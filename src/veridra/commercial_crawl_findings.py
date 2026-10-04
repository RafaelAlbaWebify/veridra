from __future__ import annotations

from collections import defaultdict
from html.parser import HTMLParser

from .core import Finding, Status
from .crawl import CrawlResult

_OVERSIZED_HTML_BYTES = 500_000


class _CommercialPageSignals(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._inside_title = False
        self._title_parts: list[str] = []
        self.description = ""
        self.missing_alt_count = 0
        self.robots_directives: set[str] = set()
        self.open_graph_properties: set[str] = set()
        self.has_structured_data = False

    @property
    def title(self) -> str:
        return " ".join(" ".join(self._title_parts).split())

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        lowered_tag = tag.lower()
        data = {key.lower(): (value or "") for key, value in attrs}
        if lowered_tag == "title":
            self._inside_title = True
        elif lowered_tag == "meta" and data.get("name", "").casefold() == "description":
            self.description = " ".join(data.get("content", "").split())
        elif lowered_tag == "meta":
            meta_name = data.get("name", "").casefold()
            if meta_name in {"robots", "googlebot", "bingbot"}:
                self.robots_directives.update(
                    directive.strip().casefold()
                    for directive in data.get("content", "").split(",")
                    if directive.strip()
                )
            property_name = data.get("property", "").casefold()
            if property_name.startswith("og:"):
                self.open_graph_properties.add(property_name)
        elif (
            lowered_tag == "script"
            and data.get("type", "").casefold() == "application/ld+json"
        ):
            self.has_structured_data = True
        elif lowered_tag == "img" and "alt" not in data:
            self.missing_alt_count += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._inside_title = False

    def handle_data(self, data: str) -> None:
        if self._inside_title:
            self._title_parts.append(data)


def _normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


def _duplicate_groups(values: dict[str, str]) -> list[dict[str, object]]:
    grouped: defaultdict[str, list[str]] = defaultdict(list)
    display_values: dict[str, str] = {}
    for url, value in values.items():
        normalized = _normalized(value)
        if not normalized:
            continue
        grouped[normalized].append(url)
        display_values.setdefault(normalized, " ".join(value.split()))
    return [
        {
            "value": display_values[normalized],
            "normalized_value": normalized,
            "urls": sorted(urls),
        }
        for normalized, urls in sorted(grouped.items())
        if len(urls) > 1
    ]


def _finding(
    *,
    identifier: str,
    title: str,
    severity: str,
    attention_summary: str,
    recommendation: str,
    affected: bool,
    evidence: dict[str, object],
    area: str | None = None,
) -> Finding:
    return Finding(
        id=identifier,
        area=area
        or (
            "Search visibility"
            if identifier.startswith("crawl.duplicate")
            else "Website health"
        ),
        title=title,
        status=Status.attention if affected else Status.passed,
        severity=severity if affected else "info",
        summary=(
            attention_summary
            if affected
            else f"No {title.lower()} issues were observed in the bounded crawl."
        ),
        recommendation=recommendation if affected else None,
        evidence=evidence,
    )


def analyze_commercial_crawl_findings(result: CrawlResult) -> list[Finding]:
    titles: dict[str, str] = {}
    descriptions: dict[str, str] = {}
    missing_alt: list[dict[str, object]] = []
    redirect_chains: list[dict[str, object]] = []
    oversized_pages: list[dict[str, object]] = []
    noindex_pages: list[dict[str, object]] = []
    missing_social_metadata: list[dict[str, object]] = []
    structured_data_urls: list[str] = []
    trust_page_urls: dict[str, list[str]] = {
        "about": [],
        "contact": [],
        "privacy": [],
        "terms": [],
    }

    for crawled in result.pages:
        page = crawled.evidence
        parser = _CommercialPageSignals()
        parser.feed(page.body)
        if parser.title:
            titles[page.final_url] = parser.title
        if parser.description:
            descriptions[page.final_url] = parser.description
        if parser.missing_alt_count:
            missing_alt.append(
                {"url": page.final_url, "missing_alt_count": parser.missing_alt_count}
            )

        header_robots = {
            directive.strip().casefold()
            for directive in page.headers.get("x-robots-tag", "").split(",")
            if directive.strip()
        }
        noindex_sources: list[str] = []
        if "noindex" in parser.robots_directives:
            noindex_sources.append("meta robots")
        if "noindex" in header_robots:
            noindex_sources.append("X-Robots-Tag")
        if noindex_sources:
            noindex_pages.append(
                {"url": page.final_url, "sources": noindex_sources}
            )

        required_social = {"og:title", "og:description"}
        missing_social = sorted(required_social - parser.open_graph_properties)
        if missing_social:
            missing_social_metadata.append(
                {"url": page.final_url, "missing_properties": missing_social}
            )

        if parser.has_structured_data:
            structured_data_urls.append(page.final_url)

        path = page.final_url.casefold().split("?", 1)[0].rstrip("/")
        route_markers = {
            "about": ("/about", "/about-us"),
            "contact": ("/contact", "/contact-us"),
            "privacy": ("/privacy", "/privacy-policy", "/data-protection"),
            "terms": ("/terms", "/terms-and-conditions", "/terms-of-service"),
        }
        for category, markers in route_markers.items():
            if any(path.endswith(marker) or f"{marker}/" in f"{path}/" for marker in markers):
                trust_page_urls[category].append(page.final_url)
        if len(page.redirect_chain) > 1:
            redirect_chains.append(
                {
                    "requested_url": page.requested_url,
                    "final_url": page.final_url,
                    "redirect_chain": list(page.redirect_chain),
                }
            )
        body_bytes = len(page.body.encode())
        if body_bytes > _OVERSIZED_HTML_BYTES:
            oversized_pages.append(
                {"url": page.final_url, "html_body_bytes": body_bytes}
            )

    duplicate_titles = _duplicate_groups(titles)
    duplicate_descriptions = _duplicate_groups(descriptions)
    missing_alt.sort(key=lambda item: str(item["url"]))
    redirect_chains.sort(key=lambda item: str(item["requested_url"]))
    oversized_pages.sort(key=lambda item: str(item["url"]))
    noindex_pages.sort(key=lambda item: str(item["url"]))
    missing_social_metadata.sort(key=lambda item: str(item["url"]))
    structured_data_urls.sort()
    for urls in trust_page_urls.values():
        urls.sort()
    missing_trust_pages = sorted(
        category for category, urls in trust_page_urls.items() if not urls
    )

    return [
        _finding(
            identifier="crawl.indexability",
            title="Indexability directives",
            severity="high",
            attention_summary=(
                f"{len(noindex_pages)} crawled pages explicitly request noindex."
            ),
            recommendation=(
                "Confirm each noindex directive is intentional and remove it from pages "
                "that should appear in search results."
            ),
            affected=bool(noindex_pages),
            evidence={
                "affected_pages": noindex_pages,
                "affected_urls": [item["url"] for item in noindex_pages],
            },
            area="Search visibility",
        ),
        _finding(
            identifier="crawl.social-metadata",
            title="Open Graph metadata coverage",
            severity="low",
            attention_summary=(
                f"{len(missing_social_metadata)} crawled pages are missing core "
                "Open Graph title or description metadata."
            ),
            recommendation=(
                "Add page-specific og:title and og:description metadata to important "
                "shareable pages."
            ),
            affected=bool(missing_social_metadata),
            evidence={
                "affected_pages": missing_social_metadata,
                "affected_urls": [item["url"] for item in missing_social_metadata],
                "required_properties": ["og:title", "og:description"],
            },
            area="Search visibility",
        ),
        _finding(
            identifier="crawl.structured-data-coverage",
            title="Structured data coverage",
            severity="low",
            attention_summary="No JSON-LD structured data was observed on crawled pages.",
            recommendation=(
                "Consider adding accurate schema.org JSON-LD where it represents real "
                "business, service, organisation or content facts."
            ),
            affected=bool(result.pages) and not structured_data_urls,
            evidence={
                "pages_with_json_ld": structured_data_urls,
                "crawled_page_count": len(result.pages),
            },
            area="Search visibility",
        ),
        _finding(
            identifier="crawl.trust-pages",
            title="Core trust pages",
            severity="medium",
            attention_summary=(
                "The bounded crawl did not observe all core trust-page categories: "
                + ", ".join(missing_trust_pages)
                + "."
            ),
            recommendation=(
                "Provide clear About, Contact, Privacy and Terms pages where applicable "
                "and make them discoverable through the site."
            ),
            affected=bool(missing_trust_pages),
            evidence={
                "observed_categories": {
                    category: urls for category, urls in trust_page_urls.items() if urls
                },
                "missing_categories": missing_trust_pages,
                "affected_urls": [],
            },
            area="Trust and content quality",
        ),
        _finding(
            identifier="crawl.duplicate-titles",
            title="Duplicate document titles",
            severity="medium",
            attention_summary=(
                f"{len(duplicate_titles)} duplicate title groups were observed."
            ),
            recommendation="Give each indexable page a distinct, descriptive document title.",
            affected=bool(duplicate_titles),
            evidence={"duplicate_groups": duplicate_titles},
        ),
        _finding(
            identifier="crawl.duplicate-descriptions",
            title="Duplicate meta descriptions",
            severity="medium",
            attention_summary=(
                f"{len(duplicate_descriptions)} duplicate meta-description groups were observed."
            ),
            recommendation="Write a distinct meta description for each important page.",
            affected=bool(duplicate_descriptions),
            evidence={"duplicate_groups": duplicate_descriptions},
        ),
        _finding(
            identifier="crawl.image-alt",
            title="Images missing alt attributes",
            severity="medium",
            attention_summary=(
                f"{len(missing_alt)} crawled pages contain images without alt attributes."
            ),
            recommendation=(
                "Add useful alt text to informative images and explicit empty alt attributes "
                "to decorative images."
            ),
            affected=bool(missing_alt),
            evidence={
                "affected_pages": missing_alt,
                "affected_urls": [item["url"] for item in missing_alt],
            },
        ),
        _finding(
            identifier="crawl.redirect-chains",
            title="Multi-hop redirect chains",
            severity="medium",
            attention_summary=(
                f"{len(redirect_chains)} crawled pages used multi-hop redirects."
            ),
            recommendation=(
                "Link directly to the final canonical URL and remove avoidable redirect hops."
            ),
            affected=bool(redirect_chains),
            evidence={"redirect_chains": redirect_chains},
        ),
        _finding(
            identifier="crawl.oversized-html",
            title="Oversized HTML responses",
            severity="medium",
            attention_summary=(
                f"{len(oversized_pages)} crawled pages exceeded the collected HTML threshold."
            ),
            recommendation=(
                "Reduce generated HTML where practical and verify the delivered document size."
            ),
            affected=bool(oversized_pages),
            evidence={
                "threshold_bytes": _OVERSIZED_HTML_BYTES,
                "measurement": "decoded collected HTML body bytes",
                "affected_pages": oversized_pages,
                "affected_urls": [item["url"] for item in oversized_pages],
            },
        ),
    ]
