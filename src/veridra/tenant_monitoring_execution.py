from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .collector import CollectionError
from .core import UnsafeTargetError
from .email_delivery import EmailAttemptStore, EmailDeliveryError, EmailStatus, send_monitoring_summary
from .identity_tenancy import RequestIdentity, TenantRole
from .service import assess_url
from .tenant_history_store import TenantHistoryStore
from .tenant_project_store import TenantProjectStore


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
        authenticated_at=None,
    )


def execute_tenant_monitoring(
    *,
    root: Path,
    tenant_id: str,
    project_id: str,
) -> TenantMonitoringExecutionResult:
    identity = _worker_identity(tenant_id)
    projects = TenantProjectStore(root)
    project = projects.load(identity, projects.ref(identity, project_id))
    try:
        assessment = assess_url(
            project.target_url,
            crawl_profile=project.resolved_crawl_profile(),
        )
    except (UnsafeTargetError, CollectionError, ValueError):
        raise

    history = TenantHistoryStore(root)
    assessment_id = history.save(identity, project_id, assessment)
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
            store=EmailAttemptStore(history.root / tenant_id / "email-deliveries"),
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
