from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .crawl_jobs import CrawlJob
from .identity_tenancy import RequestIdentity, TenantRole
from .service import assess_url
from .tenant_assessment_usage import crawled_page_count
from .tenant_history_store import TenantHistoryStore, TenantHistoryStoreError
from .tenant_project_store import TenantProjectStore, TenantProjectStoreError


class TenantCrawlExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class TenantCrawlExecutionResult:
    assessment_id: str
    pages_completed: int


def _worker_identity(tenant_id: str) -> RequestIdentity:
    return RequestIdentity(
        user_id="0" * 24,
        tenant_id=tenant_id,
        membership_role=TenantRole.owner,
        session_id="0" * 24,
        authenticated_at=datetime.now(UTC),
    )


def execute_tenant_crawl_job(
    *,
    root: Path,
    job: CrawlJob,
    progress: Callable[[int], None] | None = None,
) -> TenantCrawlExecutionResult:
    identity = _worker_identity(job.tenant_id)
    history = TenantHistoryStore(root)

    if job.assessment_id is not None:
        try:
            history.load(
                identity,
                history.ref(identity, job.project_id, job.assessment_id),
            )
        except TenantHistoryStoreError as exc:
            raise TenantCrawlExecutionError(
                "Persisted crawl-job assessment could not be reloaded."
            ) from exc
        return TenantCrawlExecutionResult(
            assessment_id=job.assessment_id,
            pages_completed=job.pages_completed,
        )

    projects = TenantProjectStore(root)
    try:
        project = projects.load(
            identity,
            projects.ref(identity, job.project_id),
        )
    except TenantProjectStoreError as exc:
        raise TenantCrawlExecutionError("Crawl-job project was not found.") from exc

    profile = project.resolved_crawl_profile()
    if project.target_url != job.target_url:
        raise TenantCrawlExecutionError(
            "Crawl-job target no longer matches the saved project."
        )
    if profile.name.value != job.crawl_profile:
        raise TenantCrawlExecutionError(
            "Crawl-job profile no longer matches the saved project."
        )
    if profile.limits.max_pages != job.page_budget:
        raise TenantCrawlExecutionError(
            "Crawl-job page budget no longer matches the saved project."
        )

    assessment = assess_url(
        project.target_url,
        crawl_profile=profile,
        crawl_progress=progress,
    )
    pages_completed = crawled_page_count(assessment)
    if pages_completed > job.page_budget:
        raise TenantCrawlExecutionError(
            "Assessment exceeded the crawl-job page budget."
        )
    try:
        assessment_id = history.save(identity, job.project_id, assessment)
    except TenantHistoryStoreError as exc:
        raise TenantCrawlExecutionError(
            "Crawl-job assessment could not be persisted."
        ) from exc
    return TenantCrawlExecutionResult(
        assessment_id=assessment_id,
        pages_completed=pages_completed,
    )
