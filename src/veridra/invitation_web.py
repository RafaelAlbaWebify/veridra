# ruff: noqa: E501
from __future__ import annotations

import hashlib
import html
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .existing_user_invitations import SQLiteExistingUserInvitationService
from .identity_tenancy import RequestIdentity, TenantRole
from .request_security import require_request_identity
from .same_origin import SameOriginRequestError, TrustedSameOriginPolicy
from .session_api import set_session_cookie
from .session_lifecycle import SessionLifecycleService
from .sqlite_identity_store import SQLiteIdentityRecordStore
from .tenant_invitations import SQLiteTenantInvitationService, TenantInvitationError

router = APIRouter(tags=["browser-invitations"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:560px;margin:56px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:12px;padding:28px}h1{margin-top:0}label{display:block;font-weight:700;margin:14px 0 5px}input{width:100%;padding:11px;border:1px solid #cfd4da;border-radius:7px}button,.button{display:inline-block;margin-top:20px;border:0;border-radius:7px;background:#22272d;color:#fff;padding:11px 16px;cursor:pointer;text-decoration:none}.muted{color:#68707a}.error{border-left:4px solid #b42318;background:#fff1f0;color:#7a271a;padding:12px;margin:0 0 16px}
"""


@dataclass(frozen=True)
class InvitationPreview:
    email: str
    tenant_id: str
    tenant_name: str
    role: TenantRole
    expires_at: datetime
    existing_user: bool


def _page(title: str, body: str, *, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='referrer' content='no-referrer'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>",
        status_code=status_code,
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Frame-Options": "DENY",
        },
    )


def _database(request: Request) -> Path:
    database = getattr(request.app.state, "veridra_identity_database", None)
    if not isinstance(database, Path):
        raise HTTPException(status_code=503, detail="Invitations are not configured.")
    return database


def _root(request: Request) -> Path | None:
    root = getattr(request.app.state, "veridra_tenant_data_root", None)
    return root if isinstance(root, Path) else None


def _store(request: Request) -> SQLiteIdentityRecordStore:
    store = getattr(request.app.state, "veridra_identity_store", None)
    if not isinstance(store, SQLiteIdentityRecordStore):
        raise HTTPException(status_code=503, detail="Invitations are not configured.")
    return store


def _trusted_origin(request: Request) -> None:
    configured = os.environ.get("VERIDRA_TRUSTED_ORIGIN", "").strip()
    if not configured:
        raise HTTPException(status_code=503, detail="Invitations are not configured.")
    try:
        TrustedSameOriginPolicy(configured).validate(request)
    except SameOriginRequestError as exc:
        raise HTTPException(status_code=403, detail="Invitation request is not permitted.") from exc


def _values(body: bytes) -> dict[str, list[str]]:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True)


def _one(values: dict[str, list[str]], name: str) -> str:
    return values.get(name, [""])[0].strip()


def _preview(request: Request, token: str) -> InvitationPreview:
    if len(token) < 32 or len(token) > 512:
        raise TenantInvitationError("Invitation is invalid or expired.")
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with sqlite3.connect(_database(request)) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """SELECT i.email, i.tenant_id, i.role, i.expires_at, i.consumed_at,
                      t.display_name AS tenant_name,
                      EXISTS(SELECT 1 FROM users u WHERE u.email = i.email) AS existing_user
               FROM tenant_invitations i
               JOIN tenants t ON t.id = i.tenant_id
               WHERE i.token_hash = ?""",
            (token_hash,),
        ).fetchone()
    if row is None or row["consumed_at"] is not None:
        raise TenantInvitationError("Invitation is invalid or expired.")
    expires_at = datetime.fromisoformat(row["expires_at"])
    if expires_at <= datetime.now(UTC):
        raise TenantInvitationError("Invitation is invalid or expired.")
    return InvitationPreview(
        email=row["email"],
        tenant_id=row["tenant_id"],
        tenant_name=row["tenant_name"],
        role=TenantRole(row["role"]),
        expires_at=expires_at,
        existing_user=bool(row["existing_user"]),
    )


def _optional_identity(request: Request) -> RequestIdentity | None:
    try:
        return require_request_identity(request)
    except HTTPException as exc:
        if exc.status_code == 401:
            return None
        raise


def _issue_session(request: Request, *, user_id: str, tenant_id: str) -> RedirectResponse:
    lifetime = timedelta(hours=8)
    issued = SessionLifecycleService(_store(request)).issue(
        user_id=user_id,
        tenant_id=tenant_id,
        lifetime=lifetime,
    )
    response = RedirectResponse("/agency", status_code=303)
    set_session_cookie(response, issued.credential, max_age=int(lifetime.total_seconds()))
    return response


def _invalid_page() -> HTMLResponse:
    return _page(
        "Invalid Veridra invitation",
        "<section><h1>Invitation is invalid or expired</h1><p class='muted'>Ask the workspace owner to send a new invitation.</p></section>",
        status_code=400,
    )


@router.get("/accept-invitation", response_class=HTMLResponse)
def accept_invitation_page(request: Request, token: str = "") -> HTMLResponse | RedirectResponse:
    try:
        preview = _preview(request, token)
    except TenantInvitationError:
        return _invalid_page()
    identity = _optional_identity(request)
    safe_token = html.escape(token, quote=True)
    tenant_name = html.escape(preview.tenant_name)
    role = html.escape(preview.role.value.replace("_", " ").title())
    if preview.existing_user:
        if identity is None:
            return_to = f"/accept-invitation?{urlencode({'token': token})}"
            return RedirectResponse(f"/login?{urlencode({'next': return_to})}", status_code=303)
        body = f"<section><h1>Join {tenant_name}</h1><p>You have been invited as <strong>{role}</strong>.</p><p class='muted'>This invitation can only be accepted by the matching authenticated account.</p><form method='post' action='/accept-invitation'><input type='hidden' name='token' value='{safe_token}'><button type='submit'>Accept invitation</button></form></section>"
        return _page("Accept Veridra invitation", body)
    body = f"<section><h1>Join {tenant_name}</h1><p>You have been invited as <strong>{role}</strong>.</p><p class='muted'>Create your Veridra account to accept this invitation.</p><form method='post' action='/accept-invitation'><input type='hidden' name='token' value='{safe_token}'><label for='display_name'>Your name</label><input id='display_name' name='display_name' maxlength='120' autocomplete='name' required><label for='password'>Password</label><input id='password' name='password' type='password' minlength='12' maxlength='1024' autocomplete='new-password' required><label for='password_confirm'>Repeat password</label><input id='password_confirm' name='password_confirm' type='password' minlength='12' maxlength='1024' autocomplete='new-password' required><button type='submit'>Create account and join</button></form></section>"
    return _page("Accept Veridra invitation", body)


@router.post("/accept-invitation", response_model=None)
async def accept_invitation_submit(request: Request) -> HTMLResponse | RedirectResponse:
    _trusted_origin(request)
    values = _values(await request.body())
    token = _one(values, "token")
    try:
        preview = _preview(request, token)
        if preview.existing_user:
            identity = require_request_identity(request)
            accepted = SQLiteExistingUserInvitationService(
                _database(request), _root(request)
            ).accept(token=token, user_id=identity.user_id)
        else:
            password = values.get("password", [""])[0]
            confirmation = values.get("password_confirm", [""])[0]
            if password != confirmation:
                return _page(
                    "Accept Veridra invitation",
                    "<section><h1>Passwords do not match</h1><p class='muted'>Return to the invitation link and try again.</p></section>",
                    status_code=400,
                )
            accepted = SQLiteTenantInvitationService(
                _database(request), _root(request)
            ).accept(
                token=token,
                display_name=_one(values, "display_name"),
                password=password,
            )
    except (TenantInvitationError, ValueError, HTTPException):
        return _invalid_page()
    return _issue_session(
        request,
        user_id=accepted.user_id,
        tenant_id=accepted.tenant_id,
    )
