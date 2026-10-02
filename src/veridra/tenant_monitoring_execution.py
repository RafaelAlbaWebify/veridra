from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .email_delivery import (
    EmailAttemptStore,
    EmailDeliveryError,
    EmailStatus,
    send_monitoring_summary,
)
from .identity_tenancy import RequestIdentity, TenantRole
from .service import assess_url
from .tenant_assessment_usage import crawled_page_count
from .tenant_history_store import TenantHistoryStore
from .tenant_project_store import TenantProjectStore
from .tenant_workspace_policy import TenantWorkspacePolicy
from .workspace_policy import UsageEvent, UsageKind


@dataclass(frozen=True)
class TenantMonitoringExecutionResult:
    assessment_id: str
    email_status: EmailStatus | None
    email_error: str | None


def _worker_identity(tenant_id: str) -> RequestIdentity:
    return RequestIdentity(
        user_id="0" * 24,
        tenant_id=tenant_id,
        membership_role=TenantRole.owner,
        session_id="0" * 24,
        authenticated_at=datetime.now(UTC),
    )


def execute_monitoring_for_identity(
    *,
    root: Path,
    identity: RequestIdentity,
    project_id: str,
    enforce_entitlements: bool = False,
) -> TenantMonitoringExecutionResult:
    projects = TenantProjectStore(root)
    project = projects.load(identity, projects.ref(identity, project_id))
    policy = TenantWorkspacePolicy(root)
    monitoring_reservation = ""
    page_reservation = ""
    ledger = policy.usage_ledger(identity)

    if enforce_entitlements and policy.workspace_store(identity).path.exists():
        workspace = policy.load(identity)
        monitoring_reservation = ledger.reserve(
            workspace,
            UsageKind.monitoring_run,
        )
        try:
            page_reservation = ledger.reserve(
                workspace,
                UsageKind.crawled_page,
                quantity=project.resolved_crawl_profile().limits.max_pages,
            )
        except Exception:
            ledger.release_reservation(monitoring_reservation)
            raise

    try:
        assessment = assess_url(
            project.target_url,
            crawl_profile=project.resolved_crawl_profile(),
        )
        history = TenantHistoryStore(root)
        assessment_id = history.save(identity, project_id, assessment)
    except Exception:
        if monitoring_reservation:
            ledger.release_reservation(monitoring_reservation)
        if page_reservation:
            ledger.release_reservation(page_reservation)
        raise

    now = datetime.now(UTC)
    if monitoring_reservation:
        ledger.record_reserved(
            monitoring_reservation,
            UsageEvent(
                kind=UsageKind.monitoring_run,
                quantity=1,
                occurred_at=now,
                related_id=assessment_id,
                note="Monitoring assessment",
            ),
        )
    if page_reservation:
        ledger.record_reserved(
            page_reservation,
            UsageEvent(
                kind=UsageKind.crawled_page,
                quantity=crawled_page_count(assessment),
                occurred_at=now,
                related_id=assessment_id,
                note="Monitoring crawl pages",
            ),
        )

    email_status: EmailStatus | None = None
    email_error: str | None = None
    try:
        attempt = send_monitoring_summary(
            project_id=project_id,
            project_name=project.name,
            target_url=project.target_url,
            assessment_id=assessment_id,
            assessment=assessment,
            recipient=(
                str(project.monitoring_email)
                if project.monitoring_email is not None
                else None
            ),
            store=EmailAttemptStore(history.root / identity.tenant_id / "email-deliveries"),
        )
        if attempt is not None:
            email_status = attempt.status
            email_error = attempt.error or None
    except EmailDeliveryError as exc:
        email_status = EmailStatus.failed
        email_error = str(exc)

    return TenantMonitoringExecutionResult(
        assessment_id=assessment_id,
        email_status=email_status,
        email_error=email_error,
    )


def execute_tenant_monitoring(
    *,
    root: Path,
    tenant_id: str,
    project_id: str,
    enforce_entitlements: bool = False,
) -> TenantMonitoringExecutionResult:
    return execute_monitoring_for_identity(
        root=root,
        identity=_worker_identity(tenant_id),
        project_id=project_id,
        enforce_entitlements=enforce_entitlements,
    )
