# ruff: noqa: E501
from __future__ import annotations

import html
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from .agency_customer_web import customer_detail as base_customer_detail
from .customer_store import CustomerRecord
from .identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .project_store import ClientProject
from .request_security import require_request_identity
from .tenant_customer_store import TenantCustomerStore, TenantCustomerStoreError
from .tenant_project_store import TenantProjectStore, TenantProjectStoreError

router = APIRouter(prefix="/agency/customers", tags=["agency-customer-projects"])


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _one(body: bytes, name: str) -> str:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True).get(name, [""])[0].strip()


def _manage_identity(request: Request) -> RequestIdentity:
    identity = require_request_identity(request)
    try:
        require_tenant_capability(identity, TenantCapability.manage_projects)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc
    return identity


def _load_customer(request: Request, identity: RequestIdentity, customer_id: str) -> CustomerRecord:
    store = TenantCustomerStore(_root(request))
    try:
        return store.load(identity, store.ref(identity, customer_id))
    except TenantCustomerStoreError as exc:
        raise HTTPException(status_code=404, detail="Customer not found.") from exc


def _replace_customer(
    request: Request,
    identity: RequestIdentity,
    customer_id: str,
    customer: CustomerRecord,
    project_id: str,
) -> None:
    if project_id in customer.project_ids:
        return
    replacement = CustomerRecord.model_validate(
        {
            **customer.model_dump(mode="json"),
            "project_ids": [*customer.project_ids, project_id],
            "updated_at": datetime.now(UTC),
        }
    )
    store = TenantCustomerStore(_root(request))
    store.replace(identity, store.ref(identity, customer_id), replacement)


def _project_section(request: Request, identity: RequestIdentity, customer_id: str, customer: CustomerRecord) -> str:
    projects = TenantProjectStore(_root(request)).list(identity)
    linked = set(customer.project_ids)
    available = [entry for entry in projects if entry.id not in linked]
    linked_rows = "".join(
        f"<li><a href='/agency/projects/{html.escape(entry.id, quote=True)}'>{html.escape(entry.name)}</a> — {html.escape(entry.target_url)}</li>"
        for entry in projects
        if entry.id in linked
    ) or "<li>No linked delivery projects yet.</li>"
    options = "".join(
        f"<option value='{html.escape(entry.id, quote=True)}'>{html.escape(entry.name)} — {html.escape(entry.target_url)}</option>"
        for entry in available
    )
    link_form = (
        f"<form method='post' action='/agency/customers/{html.escape(customer_id, quote=True)}/projects/link'>"
        f"<label for='project_id'>Existing project</label><select id='project_id' name='project_id' required>{options}</select>"
        "<p><button type='submit'>Link existing project</button></p></form>"
        if options
        else "<p class='muted'>No other existing projects are available to link.</p>"
    )
    website = html.escape(str(customer.website) if customer.website is not None else "", quote=True)
    default_name = html.escape(f"{customer.business_name} — Digital Presence", quote=True)
    create_form = f"""
    <form method='post' action='/agency/customers/{html.escape(customer_id, quote=True)}/projects/create'>
      <label for='project_name'>Project name</label>
      <input id='project_name' name='project_name' maxlength='120' value='{default_name}' required>
      <label for='target_url'>Delivery target URL</label>
      <input id='target_url' name='target_url' maxlength='2048' value='{website}' placeholder='https://client.example or staging URL' required>
      <p class='muted'>For a customer with no public website yet, use the controlled staging or future production URL that Webify will assess and manage.</p>
      <p><button type='submit'>Create and link project</button></p>
    </form>
    """
    return f"""
    <section>
      <h2>Delivery projects</h2>
      <p class='muted'>Customer/project linkage is persisted explicitly. Creating or linking here is the supported operator path.</p>
      <ul>{linked_rows}</ul>
      <div class='row'><div><h3>Create project</h3>{create_form}</div><div><h3>Link existing project</h3>{link_form}</div></div>
    </section>
    """


@router.get("/{customer_id}", response_class=HTMLResponse)
def customer_detail_with_projects(customer_id: str, request: Request) -> str:
    identity = require_request_identity(request)
    try:
        require_tenant_capability(identity, TenantCapability.view_data)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc
    customer = _load_customer(request, identity, customer_id)
    rendered = base_customer_detail(customer_id, request)
    section = _project_section(request, identity, customer_id, customer)
    marker = "</main></body></html>"
    return rendered.replace(marker, section + marker, 1)


@router.post("/{customer_id}/projects/create")
async def create_customer_project(customer_id: str, request: Request) -> RedirectResponse:
    identity = _manage_identity(request)
    customer = _load_customer(request, identity, customer_id)
    body = await request.body()
    project_name = _one(body, "project_name")
    target_url = _one(body, "target_url")
    projects = TenantProjectStore(_root(request))
    before = {entry.id for entry in projects.list(identity)}
    try:
        project = ClientProject.build(
            name=project_name,
            target_url=target_url,
            client_label=customer.business_name,
            contact_label=customer.contact_name or None,
            monitoring_email=customer.contact_email or None,
        )
        project_id = projects.save(identity, project)
        _replace_customer(request, identity, customer_id, customer, project_id)
    except (ValueError, ValidationError, TenantProjectStoreError, TenantCustomerStoreError) as exc:
        if "project_id" in locals() and project_id not in before:
            try:
                projects.delete(identity, projects.ref(identity, project_id))
            except Exception:
                pass
        raise HTTPException(status_code=400, detail="Customer project could not be created and linked.") from exc
    return RedirectResponse(f"/agency/customers/{customer_id}", status_code=303)


@router.post("/{customer_id}/projects/link")
async def link_customer_project(customer_id: str, request: Request) -> RedirectResponse:
    identity = _manage_identity(request)
    customer = _load_customer(request, identity, customer_id)
    project_id = _one(await request.body(), "project_id")
    projects = TenantProjectStore(_root(request))
    try:
        projects.load(identity, projects.ref(identity, project_id))
        _replace_customer(request, identity, customer_id, customer, project_id)
    except (TenantProjectStoreError, TenantCustomerStoreError, ValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Existing project could not be linked to this customer.") from exc
    return RedirectResponse(f"/agency/customers/{customer_id}", status_code=303)
