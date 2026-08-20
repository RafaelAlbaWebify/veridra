# ruff: noqa: E501
from __future__ import annotations

import html
import sqlite3
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .agency_navigation import agency_navigation
from .existing_user_invitations import SQLiteExistingUserInvitationService
from .identity_email_delivery import TenantInvitationDelivery
from .identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantCapability,
    TenantRole,
    require_tenant_capability,
)
from .request_security import require_request_identity
from .tenant_entitlements import bound_tenant_max_users
from .tenant_invitations import IssuedInvitation, SQLiteTenantInvitationService, TenantInvitationError

router = APIRouter(prefix="/workspace", tags=["tenant-team"])
InvitationDeliveryAdapter = Callable[[TenantInvitationDelivery], bool]

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:1080px;margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}table{width:100%;border-collapse:collapse}th,td{padding:11px;text-align:left;border-bottom:1px solid #e5e7eb;vertical-align:top}.row{display:grid;grid-template-columns:2fr 1fr;gap:12px}label{display:block;font-weight:700;margin:10px 0 5px}input,select{width:100%;padding:10px;border:1px solid #cfd4da;border-radius:7px}.button,button{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:9px 13px;text-decoration:none;cursor:pointer}.secondary{background:#59636e}.danger{background:#a23333}.muted{color:#68707a}.notice{border-left:4px solid #68707a;background:#f4f6f8;padding:12px 14px}.success{border-left-color:#16794a;background:#f0faf5}.error{border-left-color:#b42318;background:#fff1f0}.actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.agency-nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.agency-nav a{border:1px solid #cfd4da;border-radius:7px;background:#fff;color:#22272d;padding:9px 12px;text-decoration:none}.agency-nav a[aria-current='page']{background:#22272d;color:#fff;border-color:#22272d}code{overflow-wrap:anywhere}@media(max-width:760px){.row{grid-template-columns:1fr}table{display:block;overflow:auto}}
"""


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>"


def _database(request: Request) -> Path:
    store = getattr(request.app.state, "veridra_identity_store", None)
    database = getattr(store, "database", None)
    if not isinstance(database, Path):
        raise HTTPException(status_code=503, detail="Team identity storage is not configured.")
    return database


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _require(identity: RequestIdentity) -> None:
    try:
        require_tenant_capability(identity, TenantCapability.manage_memberships)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="Team management is not permitted.") from exc


def _values(body: bytes) -> dict[str, list[str]]:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True)


def _one(values: dict[str, list[str]], name: str) -> str:
    return values.get(name, [""])[0].strip()


def _members(database: Path, tenant_id: str) -> list[sqlite3.Row]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(
            """SELECT u.email, u.display_name, m.role, m.active, m.created_at
            FROM memberships m
            JOIN users u ON u.id = m.user_id
            WHERE m.tenant_id = ?
            ORDER BY m.active DESC, u.display_name, u.email""",
            (tenant_id,),
        ).fetchall()
    finally:
        connection.close()


def _existing_user(database: Path, email: str) -> bool:
    with sqlite3.connect(database) as connection:
        return connection.execute(
            "SELECT 1 FROM users WHERE email = ?",
            (email.strip().lower(),),
        ).fetchone() is not None


def _service(request: Request) -> SQLiteTenantInvitationService:
    return SQLiteTenantInvitationService(_database(request), _root(request))


def _existing_service(request: Request) -> SQLiteExistingUserInvitationService:
    return SQLiteExistingUserInvitationService(_database(request), _root(request))


def _token_page(identity: RequestIdentity, *, email: str, token: str, action: str) -> str:
    navigation = agency_navigation(identity, current="team")
    body = f"""{navigation}<section><p><a href='/workspace/members'>Team</a></p><h1>{html.escape(action)}</h1><p class='notice success'><strong>Invitation ready for {html.escape(email)}.</strong></p><p>Transactional email is not configured in this runtime. Copy this one-time token and send it to the intended recipient through a trusted channel.</p><p><code>{html.escape(token)}</code></p><p class='muted'>The token expires under the invitation policy and will not be shown again after leaving this page.</p><p><a class='button' href='/workspace/members'>Return to Team</a></p></section>"""
    return _page("Team invitation", body)


def _result_page(
    identity: RequestIdentity,
    *,
    issued: IssuedInvitation,
    action: str,
    delivered: bool | None,
) -> str:
    if delivered is None:
        return _token_page(
            identity,
            email=issued.email,
            token=issued.token,
            action=action,
        )
    navigation = agency_navigation(identity, current="team")
    if delivered:
        notice = f"<p class='notice success'><strong>Invitation email sent to {html.escape(issued.email)}.</strong></p><p class='muted'>The recipient can accept it from the secure link in the email. The invitation token is not displayed here.</p>"
    else:
        notice = f"<p class='notice error'><strong>Invitation created, but email delivery to {html.escape(issued.email)} failed.</strong></p><p class='muted'>The invitation remains active. Check SMTP delivery evidence and use Resend after the mail service is healthy.</p>"
    body = f"{navigation}<section><p><a href='/workspace/members'>Team</a></p><h1>{html.escape(action)}</h1>{notice}<p><a class='button' href='/workspace/members'>Return to Team</a></p></section>"
    return _page("Team invitation", body)


def _deliver(request: Request, issued: IssuedInvitation) -> bool | None:
    delivery = getattr(request.app.state, "veridra_tenant_invitation_delivery", None)
    if not callable(delivery):
        return None
    adapter: InvitationDeliveryAdapter = delivery
    return adapter(
        TenantInvitationDelivery(
            email=issued.email,
            token=issued.token,
            expires_at=issued.expires_at,
        )
    )


@router.get("/members", response_class=HTMLResponse)
def tenant_team(request: Request) -> str:
    identity = require_request_identity(request)
    _require(identity)
    database = _database(request)
    rows = _members(database, identity.tenant_id)
    active_count = sum(1 for row in rows if bool(row["active"]))
    root = _root(request)
    seat_limit = bound_tenant_max_users(root, identity.tenant_id) if root is not None else None
    seat_text = (
        f"{active_count} / {seat_limit} active seats"
        if seat_limit is not None
        else f"{active_count} active seats · tenant plan policy not configured"
    )
    member_rows = "".join(
        "<tr><td><strong>{name}</strong><br>{email}</td><td>{role}</td><td>{status}</td><td>{created}</td></tr>".format(
            name=html.escape(row["display_name"]),
            email=html.escape(row["email"]),
            role=html.escape(str(row["role"]).replace("_", " ").title()),
            status="Active" if bool(row["active"]) else "Inactive",
            created=html.escape(row["created_at"]),
        )
        for row in rows
    ) or "<tr><td colspan='4'>No tenant memberships were found.</td></tr>"
    invitations = _service(request).list_active(tenant_id=identity.tenant_id)
    invitation_rows = "".join(
        "<tr><td>{email}</td><td>{role}</td><td>{expires}</td><td><div class='actions'><form method='post' action='/workspace/members/invitations/{identifier}/resend'><button class='secondary' type='submit'>Resend invitation</button></form><form method='post' action='/workspace/members/invitations/{identifier}/cancel'><button class='danger' type='submit'>Cancel</button></form></div></td></tr>".format(
            email=html.escape(invitation.email),
            role=html.escape(invitation.role.value.title()),
            expires=html.escape(invitation.expires_at.isoformat()),
            identifier=html.escape(invitation.id, quote=True),
        )
        for invitation in invitations
    ) or "<tr><td colspan='4'>No active invitations.</td></tr>"
    roles = "".join(
        f"<option value='{role.value}'>{html.escape(role.value.replace('_', ' ').title())}</option>"
        for role in TenantRole
        if role is not TenantRole.owner
    )
    navigation = agency_navigation(identity, current="team")
    body = f"""{navigation}<section><p><a href='/agency'>Agency home</a></p><h1>Team</h1><p><strong>{html.escape(seat_text)}</strong></p><p class='muted'>These are real authenticated tenant memberships. Seat capacity is enforced again atomically when an invitation is accepted, so pending invitations cannot overbook the plan.</p></section><section><h2>Invite a team member</h2><form method='post' action='/workspace/members/invite'><div class='row'><div><label for='email'>Email</label><input id='email' name='email' type='email' maxlength='320' required></div><div><label for='role'>Role</label><select id='role' name='role'>{roles}</select></div></div><p class='muted'>Veridra automatically uses the authenticated existing-user flow when this email already belongs to an active account. Production sends a secure acceptance link by transactional email.</p><button type='submit'>Send invitation</button></form></section><section><h2>Members</h2><table><thead><tr><th>Member</th><th>Role</th><th>Status</th><th>Joined</th></tr></thead><tbody>{member_rows}</tbody></table></section><section><h2>Pending invitations</h2><table><thead><tr><th>Email</th><th>Role</th><th>Expires</th><th>Actions</th></tr></thead><tbody>{invitation_rows}</tbody></table></section>"""
    return _page("Tenant team", body)


@router.post("/members/invite", response_class=HTMLResponse)
async def invite_team_member(request: Request) -> str:
    identity = require_request_identity(request)
    _require(identity)
    values = _values(await request.body())
    email = _one(values, "email").lower()
    try:
        role = TenantRole(_one(values, "role"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invitation role is invalid.") from exc
    if role is TenantRole.owner:
        raise HTTPException(status_code=400, detail="Owner invitations are not permitted.")
    database = _database(request)
    try:
        if _existing_user(database, email):
            issued = _existing_service(request).issue(
                tenant_id=identity.tenant_id,
                created_by_user_id=identity.user_id,
                email=email,
                role=role,
            )
        else:
            issued = _service(request).issue(
                tenant_id=identity.tenant_id,
                created_by_user_id=identity.user_id,
                email=email,
                role=role,
            )
    except TenantInvitationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _result_page(
        identity,
        issued=issued,
        action="Invitation created",
        delivered=_deliver(request, issued),
    )


@router.post("/members/invitations/{invitation_id}/cancel")
def cancel_team_invitation(invitation_id: str, request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    _require(identity)
    try:
        _service(request).cancel(
            tenant_id=identity.tenant_id,
            invitation_id=invitation_id,
        )
    except TenantInvitationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RedirectResponse("/workspace/members", status_code=303)


@router.post("/members/invitations/{invitation_id}/resend", response_class=HTMLResponse)
def resend_team_invitation(invitation_id: str, request: Request) -> str:
    identity = require_request_identity(request)
    _require(identity)
    try:
        issued = _service(request).resend(
            tenant_id=identity.tenant_id,
            invitation_id=invitation_id,
            created_by_user_id=identity.user_id,
        )
    except TenantInvitationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _result_page(
        identity,
        issued=issued,
        action="Invitation replaced",
        delivered=_deliver(request, issued),
    )
