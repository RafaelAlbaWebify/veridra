# ruff: noqa: E501
from __future__ import annotations

import csv
import html
import io
from datetime import UTC, datetime
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from .workspace_members import (
    AuditEvent,
    AuditTrailStore,
    MemberRole,
    MemberStore,
    MemberStoreError,
    WorkspaceMember,
)
from .workspace_policy import PLAN_CATALOGUE, WorkspaceStore

router = APIRouter(prefix="/members", tags=["workspace members"])

_STYLE = """
body{font:14px Arial;margin:0;background:#f7f8fa;color:#17191c}main{max-width:1160px;margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:8px;padding:22px;margin-bottom:18px}table{width:100%;border-collapse:collapse}th,td{padding:10px;text-align:left;border-bottom:1px solid #e5e7eb;vertical-align:top}label{display:block;font-weight:700;margin:10px 0 4px}input,select{width:100%;padding:9px;border:1px solid #cfd4da}.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}.button,button{display:inline-block;background:#22272d;color:#fff;border:0;padding:9px 12px;text-decoration:none;cursor:pointer}.secondary{background:#5f6873}.danger{background:#b42318}.muted{color:#68707a}.actions{display:flex;gap:8px;flex-wrap:wrap}.status{font-weight:700}@media(max-width:760px){.row{grid-template-columns:1fr}table{display:block;overflow:auto}}
"""


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main><p><a href='/members'>Members</a> · <a href='/members/audit'>Audit trail</a> · <a href='/workspace'>Workspace</a> · <a href='/'>Assessment console</a></p>{body}</main></body></html>"


def _members() -> MemberStore:
    return MemberStore()


def _audit() -> AuditTrailStore:
    return AuditTrailStore()


def _single(body: bytes, name: str) -> str:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True).get(name, [""])[0].strip()


def _record(action: str, *, subject_id: str = "", detail: str = "") -> None:
    _audit().record(
        AuditEvent(
            action=action,
            occurred_at=datetime.now(UTC),
            actor_member_id="",
            subject_type="workspace_member",
            subject_id=subject_id,
            detail=detail,
        )
    )


def _role_options(selected: MemberRole) -> str:
    return "".join(
        f"<option value='{role.value}'{' selected' if role == selected else ''}>{html.escape(role.value.replace('_', ' ').title())}</option>"
        for role in MemberRole
    )


def _form(member: WorkspaceMember | None = None) -> str:
    first = not _members().list()
    item = member
    role = item.role if item else MemberRole.owner if first else MemberRole.analyst
    action = f"/members/{item.id}" if item else "/members"
    heading = "Edit local member" if item else "Create first local owner" if first else "Add local member"
    active = item.active if item else True
    return f"""<section><h1>{html.escape(heading)}</h1><p class='muted'>These records support local seat limits, assignments and role planning. They are not login accounts and do not provide passwords, sessions, MFA, SSO or verified identity.</p><form method='post' action='{action}'><div class='row'><div><label for='display_name'>Display name</label><input id='display_name' name='display_name' maxlength='120' required value='{html.escape(item.display_name if item else '', quote=True)}'></div><div><label for='email'>Email</label><input id='email' name='email' type='email' maxlength='320' required value='{html.escape(str(item.email) if item else '', quote=True)}'></div></div><div class='row'><div><label for='role'>Role</label><select id='role' name='role'>{_role_options(role)}</select></div><div><label>Status</label><label><input style='width:auto' type='checkbox' name='active' value='yes'{' checked' if active else ''}> Active seat</label></div></div><p><button type='submit'>Save local member</button></p></form></section>"""


def _load(member_id: str) -> WorkspaceMember:
    try:
        return _members().load(member_id)
    except MemberStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("", response_class=HTMLResponse)
def member_index() -> str:
    members = _members().list()
    workspace = WorkspaceStore().load()
    seat_limit = PLAN_CATALOGUE[workspace.plan].max_users
    active_count = sum(1 for member in members if member.active)
    rows = "".join(
        "<tr><td><strong>{name}</strong><br>{email}</td><td>{role}</td><td><span class='status'>{status}</span></td><td>{created}</td><td><div class='actions'><a class='button secondary' href='/members/{identifier}/edit'>Edit</a><form method='post' action='/members/{identifier}/delete'><button class='danger' type='submit'>Delete</button></form></div></td></tr>".format(
            name=html.escape(member.display_name),
            email=html.escape(str(member.email)),
            role=html.escape(member.role.value.title()),
            status="Active" if member.active else "Inactive",
            created=html.escape(member.created_at.isoformat()),
            identifier=member.id,
        )
        for member in members
    ) or "<tr><td colspan='5'>No local members exist. Create the first owner explicitly.</td></tr>"
    body = f"""<section><h1>Workspace members</h1><p><strong>Plan:</strong> {html.escape(workspace.plan.value.title())}<br><strong>Active seats:</strong> {active_count} / {seat_limit}</p><p class='muted'>Member roles are local operational metadata only. No request is authenticated as one of these members.</p><p><a class='button' href='/members.csv'>Export members CSV</a> <a class='button secondary' href='/members/audit.csv'>Export audit CSV</a></p></section>{_form()}<section><h2>Saved members</h2><table><thead><tr><th>Member</th><th>Role</th><th>Status</th><th>Created</th><th>Actions</th></tr></thead><tbody>{rows}</tbody></table></section>"""
    return _page("Workspace members", body)


@router.post("")
async def create_member(request: Request) -> RedirectResponse:
    body = await request.body()
    existing = _members().list()
    try:
        role = MemberRole(_single(body, "role"))
        if not existing and role != MemberRole.owner:
            raise HTTPException(status_code=400, detail="The first local member must be an owner.")
        member = WorkspaceMember.build(
            display_name=_single(body, "display_name"),
            email=_single(body, "email"),
            role=role,
            active=_single(body, "active") == "yes",
        )
        identifier = _members().save(member, WorkspaceStore().load())
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid workspace member.") from exc
    except MemberStoreError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    _record("member.created", subject_id=identifier, detail=f"Role: {member.role.value}")
    return RedirectResponse("/members", status_code=303)


@router.get("/{member_id}/edit", response_class=HTMLResponse)
def edit_member(member_id: str) -> str:
    return _page("Edit workspace member", _form(_load(member_id)))


@router.post("/{member_id}")
async def update_member(member_id: str, request: Request) -> RedirectResponse:
    current = _load(member_id)
    body = await request.body()
    try:
        updated = WorkspaceMember.model_validate(
            current.model_copy(
                update={
                    "display_name": _single(body, "display_name"),
                    "email": _single(body, "email"),
                    "role": MemberRole(_single(body, "role")),
                    "active": _single(body, "active") == "yes",
                    "updated_at": datetime.now(UTC),
                }
            )
        )
        _members().save(updated, WorkspaceStore().load())
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid workspace member update.") from exc
    except MemberStoreError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _record("member.updated", subject_id=member_id, detail=f"Role: {updated.role.value}; active: {updated.active}")
    return RedirectResponse("/members", status_code=303)


@router.post("/{member_id}/delete")
def delete_member(member_id: str) -> RedirectResponse:
    member = _load(member_id)
    try:
        _members().delete(member_id)
    except MemberStoreError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _record("member.deleted", subject_id=member_id, detail=f"Former member: {member.display_name}")
    return RedirectResponse("/members", status_code=303)


@router.get("/audit", response_class=HTMLResponse)
def audit_index() -> str:
    rows = "".join(
        "<tr><td>{time}</td><td>{action}</td><td>{subject}</td><td>{detail}</td></tr>".format(
            time=html.escape(event.occurred_at.isoformat()),
            action=html.escape(event.action),
            subject=html.escape(f"{event.subject_type}:{event.subject_id}"),
            detail=html.escape(event.detail or "—"),
        )
        for _, event in _audit().list()
    ) or "<tr><td colspan='4'>No operator audit events have been recorded.</td></tr>"
    body = f"<section><h1>Operator audit trail</h1><p class='muted'>Append-only local operational evidence. An empty actor means the action came from the unauthenticated local operator interface; it does not identify a person.</p><table><thead><tr><th>Time</th><th>Action</th><th>Subject</th><th>Detail</th></tr></thead><tbody>{rows}</tbody></table></section>"
    return _page("Operator audit trail", body)


@router.get(".csv")
def members_csv() -> Response:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["id", "display_name", "email", "role", "active", "created_at", "updated_at"])
    for member in _members().list():
        writer.writerow([member.id, member.display_name, str(member.email), member.role.value, member.active, member.created_at.isoformat(), member.updated_at.isoformat()])
    return Response(output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=veridra-members.csv"})


@router.get("/audit.csv")
def audit_csv() -> Response:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["id", "action", "occurred_at", "actor_member_id", "subject_type", "subject_id", "detail"])
    for identifier, event in _audit().list():
        writer.writerow([identifier, event.action, event.occurred_at.isoformat(), event.actor_member_id, event.subject_type, event.subject_id, event.detail])
    return Response(output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=veridra-member-audit.csv"})
