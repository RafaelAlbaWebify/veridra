# ruff: noqa: E501
from __future__ import annotations

import html
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from .agency_conversion_web import tenant_project_next_actions as base_project_overview
from .request_security import require_request_identity
from .tenant_customer_store import TenantCustomerStore
from .tenant_history_store import TenantHistoryStore

router = APIRouter(prefix="/agency", tags=["agency-project-customer"])


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


@router.get("/projects/{project_id}", response_class=HTMLResponse)
def project_overview_with_customer(
    project_id: str,
    request: Request,
    task_created: str | None = None,
) -> str:
    identity = require_request_identity(request)
    rendered = base_project_overview(project_id, request, task_created)
    root = _root(request)
    customers = TenantCustomerStore(root).list(identity)
    linked = [
        (customer_id, customer)
        for customer_id, customer in customers
        if project_id in customer.project_ids
    ]
    if not linked:
        relationship = "<p class='notice'><strong>Customer relationship:</strong> Not linked. Link this project from the customer record before treating it as customer delivery work.</p>"
    else:
        links = " · ".join(
            f"<a href='/agency/customers/{html.escape(customer_id, quote=True)}'>{html.escape(customer.business_name)}</a>"
            for customer_id, customer in linked
        )
        relationship = f"<p class='notice'><strong>Customer:</strong> {links}</p>"
    assessments = TenantHistoryStore(root).list(identity, project_id)
    project_id_html = html.escape(project_id, quote=True)
    if assessments:
        project_tools = (
            f"<p><a href='/agency/projects/{project_id_html}/progress'>Progress / Changes</a> · "
            f"<a href='/agency/projects/{project_id_html}/ai-review'>AI review exchange</a></p>"
        )
    else:
        project_tools = (
            "<p class='muted'>Progress / Changes and AI review become available after the first saved assessment.</p>"
        )
    marker = "<h1>"
    return rendered.replace(marker, relationship + project_tools + marker, 1)
