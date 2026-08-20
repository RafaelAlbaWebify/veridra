# ruff: noqa: E501
from __future__ import annotations

import html
import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .existing_user_invitations import SQLiteExistingUserInvitationService
from .request_security import require_request_identity
from .tenant_invitations import SQLiteTenantInvitationService, TenantInvitationError

router = APIRouter(tags=["invitation-acceptance-web"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:700px;margin:48px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:12px;padding:28px}h1{margin-top:0}label{display:block;font-weight:700;margin:14px 0 5px}input{width:100%;padding:11px;border:1px solid #cfd4da;border-radius:7px}button,.button{display:inline-block;margin-top:20px;border:0;border-radius:7px;background:#22272d;color:#fff;padding:11px 16px;text-decoration:none;cursor:pointer}.muted{color:#68707a}.notice{border-left:4px solid #68707a;background:#f4f6f8;padding:12px 14px}.success{border-left-color:#16794a;background:#f0faf5}.error{border-left-color:#b42318;background:#fff1f0;color:#7a271a}
"""


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>"


def _database(request: Request) -> Path:
    store = getattr(request.app.state, "veridra_identity_store", None)
    database = getattr(store, "database", None)
    if not isinstance(database, Path):
        raise HTTPException(status_code=503, detail="Invitation acceptance is not configured.")
    return database


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _values(body: bytes) -> dict[str, list[str]]:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True)


def _one(values: dict[str, list[str]], name: str) -> str:
    return values.get(name, [""])[0].strip()


def _new_service(request: Request) -> SQLiteTenantInvitationService:
    return SQLiteTenantInvitationService(_database(request), _root(request))


def _existing_service(request: Request) -> SQLiteExistingUserInvitationService:
    return SQLiteExistingUserInvitationService(_database(request), _root(request))


def _tenant_slug(database: Path, tenant_id: str) -> str:
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT slug FROM tenants WHERE id = ?",
            (tenant_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=500, detail="Accepted tenant was not found.")
    return str(row[0])


def _user_email(database: Path, user_id: str) -> str:
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT email FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=500, detail="Accepted user was not found.")
    return str(row[0])


def _new_form(token: str, error: str | None = None) -> str:
    error_html = (
        f"<p class='notice error' role='alert'>{html.escape(error)}</p>" if error else ""
    )
    body = f"""<section><h1>Join a Veridra workspace</h1><p class='muted'>This invitation creates your Veridra account and tenant membership in one transaction. The invitation is consumed only if account creation succeeds.</p>{error_html}<form method='post' action='/join'><input type='hidden' name='token' value='{html.escape(token, quote=True)}'><label for='display_name'>Your name</label><input id='display_name' name='display_name' maxlength='120' required><label for='password'>Password</label><input id='password' name='password' type='password' minlength='12' maxlength='1024' autocomplete='new-password' required><label for='password_confirm'>Repeat password</label><input id='password_confirm' name='password_confirm' type='password' minlength='12' maxlength='1024' autocomplete='new-password' required><button type='submit'>Accept invitation</button></form></section>"""
    return _page("Join Veridra", body)


def _accepted_page(*, tenant_slug: str, email: str) -> str:
    login_query = urlencode({"tenant_slug": tenant_slug, "email": email})
    body = f"""<section><h1>Invitation accepted</h1><p class='notice success'><strong>Your membership is active.</strong></p><p>Workspace slug: <code>{html.escape(tenant_slug)}</code></p><p class='muted'>Sign in using this workspace slug to enter the tenant. An existing browser session for another workspace can be replaced by signing in again.</p><a class='button' href='/login?{html.escape(login_query, quote=True)}'>Sign in to this workspace</a></section>"""
    return _page("Invitation accepted", body)


@router.get("/join", response_class=HTMLResponse)
def join_new_user(token: str) -> str:
    if len(token) < 32 or len(token) > 512:
        raise HTTPException(status_code=400, detail="Invitation token is invalid.")
    return _new_form(token)


@router.post("/join", response_model=None)
async def accept_new_user_invitation(request: Request) -> HTMLResponse:
    values = _values(await request.body())
    token = _one(values, "token")
    display_name = _one(values, "display_name")
    password = values.get("password", [""])[0]
    confirmation = values.get("password_confirm", [""])[0]
    if password != confirmation:
        return HTMLResponse(_new_form(token, "Passwords do not match."), status_code=400)
    try:
        accepted = _new_service(request).accept(
            token=token,
            display_name=display_name,
            password=password,
        )
    except (TenantInvitationError, ValueError):
        return HTMLResponse(
            _new_form(token, "Invitation is invalid, expired, used, or no seat is available."),
            status_code=400,
        )
    database = _database(request)
    return HTMLResponse(
        _accepted_page(
            tenant_slug=_tenant_slug(database, accepted.tenant_id),
            email=_user_email(database, accepted.user_id),
        )
    )


@router.get("/join/existing", response_model=None)
def join_existing_user(token: str, request: Request) -> HTMLResponse | RedirectResponse:
    if len(token) < 32 or len(token) > 512:
        raise HTTPException(status_code=400, detail="Invitation token is invalid.")
    try:
        identity = require_request_identity(request)
    except HTTPException:
        next_url = f"/join/existing?{urlencode({'token': token})}"
        return RedirectResponse(f"/login?{urlencode({'next': next_url})}", status_code=303)
    body = f"""<section><h1>Join another Veridra workspace</h1><p class='notice'><strong>Signed in account:</strong> {html.escape(identity.user_id)}</p><p>This invitation will add your authenticated account to the invited tenant. The server verifies that the invitation email matches this account and that a plan seat is available.</p><form method='post' action='/join/existing'><input type='hidden' name='token' value='{html.escape(token, quote=True)}'><button type='submit'>Accept workspace invitation</button></form></section>"""
    return HTMLResponse(_page("Join existing account", body))


@router.post("/join/existing", response_class=HTMLResponse)
async def accept_existing_user_invitation(request: Request) -> str:
    identity = require_request_identity(request)
    token = _one(_values(await request.body()), "token")
    try:
        accepted = _existing_service(request).accept(
            token=token,
            user_id=identity.user_id,
        )
    except TenantInvitationError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invitation is invalid, expired, mismatched, used, or no seat is available.",
        ) from exc
    database = _database(request)
    return _accepted_page(
        tenant_slug=_tenant_slug(database, accepted.tenant_id),
        email=_user_email(database, accepted.user_id),
    )
