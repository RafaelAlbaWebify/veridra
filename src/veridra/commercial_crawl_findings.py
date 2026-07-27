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
) -> Finding:
    return Finding(
        id=identifier,
        area="Search visibility" if identifier.startswith("crawl.duplicate") else "Website health",
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
            oversized_pages.append({"url": page.final_url, "html_body_bytes": body_bytes})

    duplicate_titles = _duplicate_groups(titles)
    duplicate_descriptions = _duplicate_groups(descriptions)
    missing_alt.sort(key=lambda item: str(item["url"]))
    redirect_chains.sort(key=lambda item: str(item["requested_url"]))
    oversized_pages.sort(key=lambda item: str(item["url"]))

    return [
        _finding(
            identifier="crawl.duplicate-titles",
            title="Duplicate document titles",
            severity="medium",
            attention_summary=f"{len(duplicate_titles)} duplicate title groups were observed.",
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
            attention_summary=f"{len(missing_alt)} crawled pages contain images without alt attributes.",
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
            attention_summary=f"{len(redirect_chains)} crawled pages used multi-hop redirects.",
            recommendation="Link directly to the final canonical URL and remove avoidable redirect hops.",
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
            recommendation="Reduce generated HTML where practical and verify the delivered document size.",
            affected=bool(oversized_pages),
            evidence={
                "threshold_bytes": _OVERSIZED_HTML_BYTES,
                "measurement": "decoded collected HTML body bytes",
                "affected_pages": oversized_pages,
                "affected_urls": [item["url"] for item in oversized_pages],
            },
        ),
    ]
