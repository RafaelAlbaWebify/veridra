from __future__ import annotations

from .identity_tenancy import TENANT_ROLE_CAPABILITIES, RequestIdentity, TenantCapability


def agency_navigation(identity: RequestIdentity, *, current: str | None = None) -> str:
    """Render the shared authenticated agency navigation for the current tenant role."""

    capabilities = TENANT_ROLE_CAPABILITIES[identity.membership_role]
    destinations: list[tuple[str, str, str]] = [
        ("home", "/agency", "Agency home"),
        ("projects", "/agency/projects", "Client projects"),
    ]
    if TenantCapability.manage_leads in capabilities:
        destinations.append(("leads", "/agency/leads", "Leads"))
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
