from __future__ import annotations

from collections import defaultdict
from html.parser import HTMLParser

from .core import Finding, Status
from .crawl import CrawlResult

_OVERSIZED_HTML_BYTES = 500_000


class _QualitySignals(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.description = ""
        self.missing_alt_images = 0
        self._inside_title = False

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        data = {key.lower(): value for key, value in attrs}
        if tag == "title":
            self._inside_title = True
        if tag == "meta" and (data.get("name") or "").lower() == "description":
            self.description = (data.get("content") or "").strip()
        if tag == "img" and "alt" not in data:
            self.missing_alt_images += 1

    def handle_data(self, data: str) -> None:
        if self._inside_title:
            self.title_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._inside_title = False

    @property
    def title(self) -> str:
        return " ".join("".join(self.title_parts).split())


def _duplicate_groups(values: dict[str, list[str]]) -> list[dict[str, object]]:
    return [
        {"value": value, "urls": sorted(urls), "count": len(urls)}
        for value, urls in sorted(values.items())
        if value and len(urls) > 1
    ]


def _finding(
    identifier: str,
    title: str,
    area: str,
    severity: str,
    passed: bool,
    summary: str,
    recommendation: str,
    evidence: dict[str, object],
) -> Finding:
    return Finding(
        id=identifier,
        area=area,
        title=title,
        status=Status.passed if passed else Status.attention,
        severity="info" if passed else severity,
        summary=summary,
        recommendation=None if passed else recommendation,
        evidence=evidence,
    )


def analyze_page_quality(result: CrawlResult) -> list[Finding]:
    titles: defaultdict[str, list[str]] = defaultdict(list)
    descriptions: defaultdict[str, list[str]] = defaultdict(list)
    missing_alt: list[dict[str, object]] = []
    redirect_chains: list[dict[str, object]] = []
    oversized_pages: list[dict[str, object]] = []

    for crawled in result.pages:
        page = crawled.evidence
        parser = _QualitySignals()
        parser.feed(page.body)
        if parser.title:
            titles[parser.title].append(page.final_url)
        if parser.description:
            descriptions[parser.description].append(page.final_url)
        if parser.missing_alt_images:
            missing_alt.append(
                {
                    "url": page.final_url,
                    "missing_alt_images": parser.missing_alt_images,
                }
            )
        if len(page.redirect_chain) > 1:
            redirect_chains.append(
                {
                    "requested_url": page.requested_url,
                    "final_url": page.final_url,
                    "redirect_chain": list(page.redirect_chain),
                    "hop_count": len(page.redirect_chain),
                }
            )
        body_bytes = len(page.body.encode("utf-8"))
        if body_bytes > _OVERSIZED_HTML_BYTES:
            oversized_pages.append(
                {
                    "url": page.final_url,
                    "html_body_bytes": body_bytes,
                }
            )

    duplicate_titles = _duplicate_groups(titles)
    duplicate_descriptions = _duplicate_groups(descriptions)
    crawled_pages = len(result.pages)

    return [
        _finding(
            "crawl.duplicate-titles",
            "Duplicate document titles",
            "Search visibility",
            "medium",
            not duplicate_titles,
            (
                "No duplicate non-empty document titles were observed."
                if not duplicate_titles
                else f"{len(duplicate_titles)} duplicate title groups were observed."
            ),
            "Give each indexable page a specific, descriptive document title.",
            {"duplicate_groups": duplicate_titles, "crawled_pages": crawled_pages},
        ),
        _finding(
            "crawl.duplicate-descriptions",
            "Duplicate meta descriptions",
            "Search visibility",
            "medium",
            not duplicate_descriptions,
            (
                "No duplicate non-empty meta descriptions were observed."
                if not duplicate_descriptions
                else (
                    f"{len(duplicate_descriptions)} duplicate description groups "
                    "were observed."
                )
            ),
            "Write a useful page-specific meta description for each indexable page.",
            {
                "duplicate_groups": duplicate_descriptions,
                "crawled_pages": crawled_pages,
            },
        ),
        _finding(
            "crawl.image-alt",
            "Image alternative text",
            "Accessibility",
            "medium",
            not missing_alt,
            (
                "All crawled image elements included an alt attribute."
                if not missing_alt
                else f"{len(missing_alt)} crawled pages contain images without alt attributes."
            ),
            (
                "Add meaningful alt text to informative images and an explicit empty alt "
                "attribute to decorative images."
            ),
            {"affected_pages": missing_alt, "crawled_pages": crawled_pages},
        ),
        _finding(
            "crawl.redirect-chains",
            "Internal redirect chains",
            "Website health",
            "medium",
            not redirect_chains,
            (
                "No multi-hop redirect chains were observed on crawled targets."
                if not redirect_chains
                else f"{len(redirect_chains)} multi-hop redirect chains were observed."
            ),
            "Update internal links to point directly to their final canonical destinations.",
            {"chains": redirect_chains, "crawled_pages": crawled_pages},
        ),
        _finding(
            "crawl.page-size",
            "Oversized HTML documents",
            "Website health",
            "low",
            not oversized_pages,
            (
                f"No crawled HTML body exceeded {_OVERSIZED_HTML_BYTES} bytes."
                if not oversized_pages
                else f"{len(oversized_pages)} HTML bodies exceeded the review threshold."
            ),
            "Reduce unnecessary HTML payload while preserving required page content.",
            {
                "threshold_html_body_bytes": _OVERSIZED_HTML_BYTES,
                "affected_pages": oversized_pages,
                "measurement": "decoded HTML body encoded as UTF-8; not browser transfer size",
                "crawled_pages": crawled_pages,
            },
        ),
    ]
