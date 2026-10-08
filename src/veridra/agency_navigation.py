from __future__ import annotations

import html
import os

from .agency_ui import agency_design_system
from .identity_tenancy import (
    TENANT_ROLE_CAPABILITIES,
    RequestIdentity,
    TenantCapability,
)
from .runtime_config import local_agency_mode_enabled

_NAV_HELP = {
    "home": "Return to the operator command center and see the recommended workflow.",
    "prospect-discovery": "Find businesses to review before they enter the sales pipeline.",
    "market-studies": "Research multiple sectors in a city and review opportunities.",
    "prospects": "Review saved prospects, qualification evidence and follow-up state.",
    "deals": "Manage sales conversations, proposals and commercial progression.",
    "customers": "Open accepted customers and their onboarding or account state.",
    "projects": "Open delivery projects for assessments, remediation, reports and proof.",
    "recurring": "Manage recurring Presence Care services after delivery.",
    "leads": "Review inbound leads captured through supported Webify workflows.",
    "lead-forms": "Manage Webify-branded website-audit lead forms.",
    "workspace": "Review hosted-plan limits and usage.",
    "billing": "Manage hosted VERIDRA subscription billing.",
    "team": "Manage hosted workspace members.",
}


def agency_navigation(identity: RequestIdentity, *, current: str | None = None) -> str:
    """Render the shared authenticated agency navigation for the current tenant role."""

    capabilities = TENANT_ROLE_CAPABILITIES[identity.membership_role]
    operator_mode = os.environ.get("VERIDRA_ENV", "").strip().lower() == "operator"
    local_agency_mode = local_agency_mode_enabled()
    webify_mode = operator_mode or local_agency_mode
    groups: list[tuple[str, list[tuple[str, str, str]]]] = [
        ("Overview", [("home", "/agency", "Home")]),
    ]

    if webify_mode:
        if TenantCapability.manage_leads in capabilities:
            groups.append(
                (
                    "Sales",
                    [
                        ("market-studies", "/agency/prospects/discover/market", "Market studies"),
                        ("prospect-discovery", "/agency/prospects/discover", "Find prospects"),
                        ("prospects", "/agency/prospects", "Prospects"),
                        ("deals", "/agency/deals", "Sales / proposals"),
                    ],
                )
            )
        groups.append(
            (
                "Clients",
                [
                    ("customers", "/agency/customers", "Customers"),
                    ("projects", "/agency/projects", "Client projects"),
                    ("recurring", "/agency/recurring-services", "Presence Care"),
                ],
            )
        )
        if local_agency_mode and TenantCapability.manage_leads in capabilities:
            groups.append(
                (
                    "Lead generation",
                    [
                        ("leads", "/agency/leads", "Inbound leads"),
                        ("lead-forms", "/agency/lead-forms", "Lead forms"),
                    ],
                )
            )
    else:
        groups.append(
            (
                "Audit & delivery",
                [
                    ("projects", "/agency/projects", "Client projects"),
                ],
            )
        )
        if TenantCapability.manage_leads in capabilities:
            groups.append(
                (
                    "Lead generation",
                    [
                        ("leads", "/agency/leads", "Inbound leads"),
                        ("lead-forms", "/agency/lead-forms", "Lead forms"),
                    ],
                )
            )
        workspace: list[tuple[str, str, str]] = []
        if TenantCapability.manage_tenant in capabilities:
            workspace.extend(
                [
                    ("workspace", "/workspace", "Plan and usage"),
                    ("billing", "/billing", "Billing"),
                ]
            )
        if TenantCapability.manage_memberships in capabilities:
            workspace.append(("team", "/workspace/members", "Team"))
        if workspace:
            groups.append(("Workspace", workspace))

    workspace_label = (
        "Webify operator"
        if operator_mode
        else ("Webify local agency" if local_agency_mode else "Agency workspace")
    )

    links: list[str] = []
    for _group_label, destinations in groups:
        for key, href, item_label in destinations:
            help_text = html.escape(_NAV_HELP.get(key, item_label), quote=True)
            current_attr = " aria-current='page'" if key == current else ""
            links.append(
                f"<a href='{href}'{current_attr} title='{help_text}' "
                f"data-help='{help_text}'>{html.escape(item_label)}</a>"
            )

    if operator_mode:
        context = (
            "<div class='nav-context' aria-label='Operator context'>"
            "<span class='status-chip ok'>Local runtime</span>"
            "<span class='status-chip guard' title='Real outreach remains compliance-controlled'>"
            "Outreach controlled</span></div>"
        )
    elif local_agency_mode:
        context = (
            "<div class='nav-context' aria-label='Workspace context'>"
            "<span class='status-chip ok'>Local agency</span></div>"
        )
    else:
        context = (
            "<div class='nav-context' aria-label='Workspace context'>"
            "<span class='status-chip'>Hosted workspace</span></div>"
        )

    return (
        agency_design_system()
        + "<nav class='agency-nav' aria-label='Agency navigation'>"
        + f"<div class='nav-brand'>VERIDRA<small>{html.escape(workspace_label)}</small></div>"
        + "<div class='nav-links'>"
        + "".join(links)
        + "</div>"
        + context
        + "</nav>"
    )
