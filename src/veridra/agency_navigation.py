from __future__ import annotations

import os

from .identity_tenancy import (
    TENANT_ROLE_CAPABILITIES,
    RequestIdentity,
    TenantCapability,
)
from .runtime_config import local_agency_mode_enabled

_NAV_STYLE = """
<style>
:root{--veridra-sidebar-width:244px}
body>main{
    max-width:none!important;
    margin:0!important;
    padding:28px 32px 48px calc(var(--veridra-sidebar-width) + 36px)!important;
}
.agency-nav{
    position:fixed;
    inset:0 auto 0 0;
    width:var(--veridra-sidebar-width);
    z-index:20;
    display:flex!important;
    flex-direction:column;
    gap:3px!important;
    margin:0!important;
    padding:22px 14px;
    overflow-y:auto;
    background:#17191c;
    border-right:1px solid #2b3036;
}
.agency-nav .nav-brand{
    display:block;
    margin:0 8px 18px;
    color:#fff;
    font-size:17px;
    font-weight:700;
    letter-spacing:.01em;
}
.agency-nav .nav-brand small{
    display:block;
    margin-top:4px;
    color:#9da6b0;
    font-size:11px;
    font-weight:400;
    text-transform:uppercase;
    letter-spacing:.08em;
}
.agency-nav .nav-group{
    margin:12px 8px 5px;
    color:#8e98a3;
    font-size:10px;
    font-weight:700;
    text-transform:uppercase;
    letter-spacing:.09em;
}
.agency-nav a{
    display:block!important;
    width:100%;
    border:0!important;
    border-radius:7px!important;
    background:transparent!important;
    color:#d7dce1!important;
    padding:9px 10px!important;
    text-decoration:none!important;
}
.agency-nav a:hover{background:#252a30!important;color:#fff!important}
.agency-nav a[aria-current='page']{
    background:#343a41!important;
    color:#fff!important;
    border:0!important;
}
@media(min-width:1200px) and (min-height:800px){
    body:has(.agency-workbench){overflow:hidden}
    body>main:has(.agency-workbench){
        height:100vh;
        overflow:hidden;
        padding-top:18px!important;
        padding-bottom:18px!important;
    }
    .agency-workbench{
        display:flex;
        flex-direction:column;
        gap:10px;
        height:100%;
        min-height:0;
    }
    .agency-workbench>section{
        margin:0!important;
    }
    .workbench-head{
        flex:0 0 auto;
        padding:16px 18px!important;
    }
    .workbench-head h1{
        margin:0 0 6px;
    }
    .workbench-head p{
        margin:4px 0;
    }
    .workbench-body{
        flex:1 1 auto;
        min-height:0;
        overflow:hidden;
        padding:0!important;
    }
    .workbench-scroll{
        height:100%;
        min-height:0;
        overflow:auto;
        padding:14px 18px;
    }
    .workbench-scroll table{
        margin:0;
    }
    .workbench-scroll thead th{
        position:sticky;
        top:0;
        z-index:2;
        background:#fff;
    }
    .workbench-cards{
        height:100%;
        min-height:0;
        overflow:auto;
        padding:14px 18px;
    }
    .workbench-split{
        display:grid;
        grid-template-columns:minmax(0,2fr) minmax(280px,1fr);
        gap:10px;
        height:100%;
        min-height:0;
    }
    .workbench-pane{
        min-height:0;
        overflow:auto;
        background:#fff;
        border:1px solid #dfe3e8;
        border-radius:10px;
        padding:14px 18px;
    }
    .workbench-toolbar{
        display:flex;
        align-items:end;
        gap:8px;
        flex-wrap:wrap;
    }
}
@media(max-width:900px){
    body>main{
        padding:18px!important;
    }
    .agency-nav{
        position:static;
        width:auto;
        flex-direction:row;
        flex-wrap:wrap;
        padding:10px;
        margin-bottom:18px!important;
        border:0;
        border-radius:10px;
    }
    .agency-nav .nav-brand{width:100%;margin:4px 8px 8px}
    .agency-nav .nav-brand small{display:inline;margin-left:8px}
    .agency-nav .nav-group{display:none}
    .agency-nav a{width:auto;padding:8px 10px!important}
}
</style>
"""


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
    sections: list[str] = [
        f"<div class='nav-brand'>VERIDRA<small>{workspace_label}</small></div>"
    ]
    for label, destinations in groups:
        links = "".join(
            "<a href='{href}'{current_attr}>{label}</a>".format(
                href=href,
                current_attr=" aria-current='page'" if key == current else "",
                label=item_label,
            )
            for key, href, item_label in destinations
        )
        sections.append(f"<div class='nav-group'>{label}</div>{links}")

    return (
        _NAV_STYLE
        + "<nav class='agency-nav' aria-label='Agency navigation'>"
        + "".join(sections)
        + "</nav>"
    )
