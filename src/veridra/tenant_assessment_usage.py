from __future__ import annotations

from pathlib import Path

from fastapi import Request

from . import app as app_module
from .core import Assessment
from .crawl_profiles import anonymous_crawl_profile
from .identity_tenancy import RequestIdentity
from .tenant_entitlements import (
    record_tenant_usage,
    reserve_tenant_usage,
    tenant_workspace_active,
)
from .tenant_workspace_policy import TenantWorkspacePolicy
from .workspace_policy import UsageKind


def _identity(request: Request) -> RequestIdentity | None:
    candidate = getattr(request.state, "veridra_verified_identity", None)
    return candidate if isinstance(candidate, RequestIdentity) else None


def _policy(request: Request) -> TenantWorkspacePolicy:
    configured = getattr(request.app.state, "veridra_tenant_data_root", None)
    root = configured if isinstance(configured, Path) else None
    return TenantWorkspacePolicy(root)


def crawled_page_count(assessment: Assessment) -> int:
    for finding in assessment.findings:
        if finding.id != "crawl.http-status":
            continue
        value = finding.evidence.get("crawled_pages")
        if isinstance(value, int) and value > 0:
            return value
    return 1


def assess_for_request(request: Request, url: str) -> Assessment:
    identity = _identity(request)
    policy = _policy(request)
    active = identity is not None and tenant_workspace_active(policy, identity)
    if active and identity is not None:
        reserve_tenant_usage(policy, identity, UsageKind.audit)
        reserve_tenant_usage(
            policy,
            identity,
            UsageKind.crawled_page,
            quantity=anonymous_crawl_profile().limits.max_pages,
        )
    assessment = app_module.assess_url(url)
    if active and identity is not None:
        related_id = str(assessment.target)
        record_tenant_usage(
            policy,
            identity,
            UsageKind.audit,
            related_id=related_id,
            note="Authenticated website assessment",
        )
        record_tenant_usage(
            policy,
            identity,
            UsageKind.crawled_page,
            quantity=crawled_page_count(assessment),
            related_id=related_id,
            note="Successful bounded crawl pages",
        )
    return assessment
