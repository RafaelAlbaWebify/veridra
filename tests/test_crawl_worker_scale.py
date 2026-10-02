from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from veridra.collector import PageEvidence
from veridra.crawl import CrawlLimits, crawl_site
from veridra.crawl_jobs import CrawlJobState, SQLiteCrawlJobStore
from veridra.crawl_worker import CrawlWorker
from veridra.tenant_crawl_execution import TenantCrawlExecutionResult

NOW = datetime(2026, 10, 2, 14, 0, tzinfo=UTC)
TENANT = "a" * 24
PROJECT = "b" * 24


def _page(
    url: str,
    body: str,
    *,
    content_type: str = "text/html",
) -> PageEvidence:
    return PageEvidence(
        requested_url=url,
        final_url=url,
        status_code=200,
        headers={"content-type": content_type},
        body=body,
        redirect_chain=(),
        connected_ip="93.184.216.34",
        validated_ips=("93.184.216.34",),
    )


def test_crawl_worker_runs_bounded_500_page_workload_outside_http_request(
    tmp_path: Path,
) -> None:
    root = tmp_path / "tenants"
    store = SQLiteCrawlJobStore(root / "crawl-jobs.sqlite3")
    job = store.enqueue(
        tenant_id=TENANT,
        project_id=PROJECT,
        target_url="https://example.com/",
        crawl_profile="scale-fixture",
        page_budget=500,
        request_key="scale:500",
        now=NOW,
        max_active_for_tenant=1,
    )

    sitemap_urls = ["https://example.com/"] + [
        f"https://example.com/page-{index}"
        for index in range(1, 500)
    ]
    sitemap = (
        "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
        + "".join(f"<url><loc>{url}</loc></url>" for url in sitemap_urls)
        + "</urlset>"
    )
    calls: list[str] = []

    def collector(url: str, **_: object) -> PageEvidence:
        calls.append(url)
        if url == "https://example.com/sitemap.xml":
            return _page(url, sitemap, content_type="application/xml")
        return _page(
            url,
            "<html><head><title>Scale worker</title></head>"
            "<body><h1>Scale worker</h1></body></html>",
        )

    def execute(
        *,
        root: Path,
        job: object,
        progress: object,
    ) -> TenantCrawlExecutionResult:
        del root, job
        assert callable(progress)
        result = crawl_site(
            "https://example.com/",
            limits=CrawlLimits(
                max_pages=500,
                max_depth=0,
                max_total_bytes=20_000_000,
                per_page_bytes=250_000,
                timeout=2.0,
                max_sitemaps=1,
                max_sitemap_urls=500,
            ),
            collector=collector,
            progress_callback=progress,
        )
        assert len(result.pages) == 500
        return TenantCrawlExecutionResult(
            assessment_id="e" * 24,
            pages_completed=len(result.pages),
        )

    result = CrawlWorker(
        root=root,
        store=store,
        execute=execute,
        clock=lambda: NOW,
    ).run_once(limit=1)

    final = store.load(tenant_id=TENANT, job_id=job.id)

    assert result.leased == 1
    assert result.succeeded == 1
    assert result.retried == 0
    assert result.failed == 0
    assert final.state is CrawlJobState.succeeded
    assert final.pages_completed == 500
    assert final.assessment_id == "e" * 24
    assert len(calls) == 501
