# ruff: noqa: E501
from __future__ import annotations

import html
import os
import sqlite3
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .identity_bootstrap import BOOTSTRAP_CONFIRMATION, IdentityBootstrapError, SQLiteIdentityBootstrap
from .same_origin import SameOriginRequestError, TrustedSameOriginPolicy
from .session_api import set_session_cookie
from .session_lifecycle import SessionLifecycleService
from .sqlite_identity_store import SQLiteIdentityRecordStore

router = APIRouter(tags=["onboarding"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:760px;margin:48px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:12px;padding:28px}h1{margin-top:0}label{display:block;font-weight:700;margin:14px 0 5px}input{width:100%;padding:11px;border:1px solid #cfd4da;border-radius:7px}button{margin-top:20px;border:0;border-radius:7px;background:#22272d;color:#fff;padding:11px 16px;cursor:pointer}.muted{color:#68707a}.error{border-left:4px solid #b42318;background:#fff1f0;color:#7a271a;padding:12px;margin-bottom:16px}
"""


def _page(error: str | None = None) -> str:
    error_html = f"<div class='error' role='alert'>{html.escape(error)}</div>" if error else ""
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Set up Veridra</title><style>{_STYLE}</style></head><body><main><section><h1>Create your Veridra agency workspace</h1><p class='muted'>This one-time form creates the first tenant owner and starts the workspace on the Free plan. It does not create a payment or subscription.</p>{error_html}<form method='post' action='/onboarding'><label for='tenant_name'>Agency or organisation name</label><input id='tenant_name' name='tenant_name' maxlength='120' required><label for='tenant_slug'>Workspace slug</label><input id='tenant_slug' name='tenant_slug' minlength='3' maxlength='80' pattern='[a-z0-9]+(?:-[a-z0-9]+)*' required><label for='owner_name'>Your name</label><input id='owner_name' name='owner_name' maxlength='120' required><label for='owner_email'>Email</label><input id='owner_email' name='owner_email' type='email' maxlength='254' required><label for='password'>Password</label><input id='password' name='password' type='password' minlength='12' maxlength='1024' autocomplete='new-password' required><label for='password_confirm'>Repeat password</label><input id='password_confirm' name='password_confirm' type='password' minlength='12' maxlength='1024' autocomplete='new-password' required><button type='submit'>Create agency workspace</button></form></section></main></body></html>"""


def _database(request: Request) -> Path:
    value = getattr(request.app.state, "veridra_identity_database", None)
    if not isinstance(value, Path):
        raise HTTPException(status_code=503, detail="Onboarding is not configured.")
    return value


def _identity_store(request: Request) -> SQLiteIdentityRecordStore:
    value = getattr(request.app.state, "veridra_identity_store", None)
    if not isinstance(value, SQLiteIdentityRecordStore):
        raise HTTPException(status_code=503, detail="Onboarding is not configured.")
    return value


def _tenant_root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _is_empty(database: Path) -> bool:
    with sqlite3.connect(database) as connection:
        tenants = int(connection.execute("SELECT COUNT(*) FROM tenants").fetchone()[0])
        users = int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])
    return tenants == 0 and users == 0


def _require_available(request: Request) -> Path:
    database = _database(request)
    if not _is_empty(database):
        raise HTTPException(status_code=404, detail="Onboarding is not available.")
    return database


def _trusted_origin(request: Request) -> None:
    configured = os.environ.get("VERIDRA_TRUSTED_ORIGIN", "").strip()
    if not configured:
        raise HTTPException(status_code=503, detail="Onboarding is not configured.")
    try:
        TrustedSameOriginPolicy(configured).validate(request)
    except SameOriginRequestError as exc:
        raise HTTPException(status_code=403, detail="Onboarding request is not permitted.") from exc


def _values(body: bytes) -> dict[str, list[str]]:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True)


def _one(values: dict[str, list[str]], name: str) -> str:
    return values.get(name, [""])[0].strip()


@router.get("/onboarding", response_class=HTMLResponse)
def onboarding(request: Request) -> str:
    _require_available(request)
    return _page()


@router.post("/onboarding", response_model=None)
async def create_onboarding(request: Request) -> HTMLResponse | RedirectResponse:
    database = _require_available(request)
    _trusted_origin(request)
    values = _values(await request.body())
    password = values.get("password", [""])[0]
    confirmation = values.get("password_confirm", [""])[0]
    if password != confirmation:
        return HTMLResponse(_page("Passwords do not match."), status_code=400)
    try:
        result = SQLiteIdentityBootstrap(database, tenant_data_root=_tenant_root(request)).create_first_owner(
            tenant_slug=_one(values, "tenant_slug"),
            tenant_name=_one(values, "tenant_name"),
            owner_email=_one(values, "owner_email"),
            owner_name=_one(values, "owner_name"),
            password=password,
            confirmation=BOOTSTRAP_CONFIRMATION,
        )
    except (IdentityBootstrapError, ValueError) as exc:
        return HTMLResponse(_page(str(exc)), status_code=400)
    lifetime = timedelta(hours=8)
    issued = SessionLifecycleService(_identity_store(request)).issue(
        user_id=result.user_id,
        tenant_id=result.tenant_id,
        lifetime=lifetime,
    )
    response = RedirectResponse("/agency", status_code=303)
    set_session_cookie(response, issued.credential, max_age=int(lifetime.total_seconds()))
    return response
