from __future__ import annotations

from .identity_tenancy import TENANT_ROLE_CAPABILITIES, RequestIdentity, TenantCapability


def agency_navigation(identity: RequestIdentity, *, current: str | None = None) -> str:
    """Render the shared authenticated agency navigation for the current tenant role."""

    capabilities = TENANT_ROLE_CAPABILITIES[identity.membership_role]
    destinations: list[tuple[str, str, str]] = [
        ("home", "/agency", "Agency home"),
        ("commercial", "/agency/commercial", "Commercial"),
        ("customers", "/agency/customers", "Customers"),
        ("projects", "/agency/projects", "Client projects"),
    ]
    if TenantCapability.manage_leads in capabilities:
        destinations.append(("prospects", "/agency/prospects", "Prospects"))
        destinations.append(("deals", "/agency/deals", "Sales / proposals"))
        destinations.append(
            ("prospect-discovery", "/agency/prospects/discover", "Discover prospects")
        )
        destinations.append(("leads-import", "/agency/prospects/import", "Import LEADS"))
        destinations.append(("leads", "/agency/leads", "Inbound leads"))
        destinations.append(("lead-forms", "/agency/lead-forms", "Lead forms"))
    if TenantCapability.manage_tenant in capabilities:
        destinations.append(("workspace", "/workspace", "Plan and usage"))
    if TenantCapability.manage_memberships in capabilities:
        destinations.append(("team", "/workspace/members", "Team"))

    links = "".join(
        "<a href='{href}'{current_attr}>{label}</a>".format(
            href=href,
            current_attr=" aria-current='page'" if key == current else "",
            label=label,
        )
        for key, href, label in destinations
    )
    return f"<nav class='agency-nav' aria-label='Agency navigation'>{links}</nav>"
