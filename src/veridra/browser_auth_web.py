# ruff: noqa: E501
from __future__ import annotations

import html
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .login_throttle import SQLiteLoginThrottle
from .password_auth import SQLitePasswordAuthenticator
from .password_recovery import PasswordRecoveryError, SQLitePasswordRecoveryService
from .password_recovery_api import PasswordResetDelivery
from .same_origin import SameOriginRequestError, TrustedSameOriginPolicy
from .session_api import set_session_cookie
from .session_lifecycle import SessionLifecycleService
from .sqlite_identity_store import SQLiteIdentityRecordStore

router = APIRouter(tags=["browser-authentication"])
PasswordResetDeliveryAdapter = Callable[[PasswordResetDelivery], None]

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:520px;margin:56px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:12px;padding:28px}h1{margin-top:0}label{display:block;font-weight:700;margin:14px 0 5px}input{width:100%;padding:11px;border:1px solid #cfd4da;border-radius:7px}button{margin-top:20px;border:0;border-radius:7px;background:#22272d;color:#fff;padding:11px 16px;cursor:pointer}.muted{color:#68707a}.error{border-left:4px solid #b42318;background:#fff1f0;color:#7a271a;padding:12px;margin:0 0 16px}.success{border-left:4px solid #16794a;background:#f0faf5;color:#0d5c38;padding:12px;margin:0 0 16px}.links{margin-top:18px;display:flex;gap:14px;flex-wrap:wrap}a{color:#2457a6}
"""


def _page(title: str, content: str) -> HTMLResponse:
    document = f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='referrer' content='no-referrer'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main>{content}</main></body></html>"
    return HTMLResponse(
        document,
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Frame-Options": "DENY",
        },
    )


def _values(body: bytes) -> dict[str, list[str]]:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True)


def _one(values: dict[str, list[str]], name: str) -> str:
    return values.get(name, [""])[0].strip()


def _database(request: Request) -> Path:
    value = getattr(request.app.state, "veridra_identity_database", None)
    if not isinstance(value, Path):
        raise HTTPException(status_code=503, detail="Authentication is not configured.")
    return value


def _services(
    request: Request,
) -> tuple[SQLitePasswordAuthenticator, SessionLifecycleService, SQLiteLoginThrottle]:
    authenticator = getattr(request.app.state, "veridra_password_authenticator", None)
    identity_store = getattr(request.app.state, "veridra_identity_store", None)
    login_throttle = getattr(request.app.state, "veridra_login_throttle", None)
    if (
        not isinstance(authenticator, SQLitePasswordAuthenticator)
        or not isinstance(identity_store, SQLiteIdentityRecordStore)
        or not isinstance(login_throttle, SQLiteLoginThrottle)
    ):
        raise HTTPException(status_code=503, detail="Authentication is not configured.")
    return authenticator, SessionLifecycleService(identity_store), login_throttle


def _trusted_origin(request: Request) -> None:
    configured = os.environ.get("VERIDRA_TRUSTED_ORIGIN", "").strip()
    if not configured:
        raise HTTPException(status_code=503, detail="Authentication is not configured.")
    try:
        TrustedSameOriginPolicy(configured).validate(request)
    except SameOriginRequestError as exc:
        raise HTTPException(status_code=403, detail="Authentication request is not permitted.") from exc


def _login_form(error: str = "", *, reset_complete: bool = False) -> HTMLResponse:
    notice = ""
    if reset_complete:
        notice = "<div class='success' role='status'>Password updated. Sign in with your new password.</div>"
    elif error:
        notice = f"<div class='error' role='alert'>{html.escape(error)}</div>"
    return _page(
        "Sign in to Veridra",
        f"<section><h1>Sign in to Veridra</h1><p class='muted'>Open your agency workspace.</p>{notice}<form method='post' action='/login'><label for='tenant_slug'>Workspace slug</label><input id='tenant_slug' name='tenant_slug' minlength='3' maxlength='80' pattern='[a-z0-9]+(?:-[a-z0-9]+)*' autocomplete='organization' required><label for='email'>Email</label><input id='email' name='email' type='email' maxlength='254' autocomplete='username' required><label for='password'>Password</label><input id='password' name='password' type='password' maxlength='1024' autocomplete='current-password' required><button type='submit'>Sign in</button></form><div class='links'><a href='/forgot-password'>Forgot password?</a><a href='/onboarding'>First-time setup</a></div></section>",
    )


def _forgot_form(*, submitted: bool = False) -> HTMLResponse:
    notice = ""
    if submitted:
        notice = "<div class='success' role='status'>If an active account exists for that email, reset instructions have been sent.</div>"
    return _page(
        "Reset your Veridra password",
        f"<section><h1>Reset your password</h1><p class='muted'>Enter the email address used for your Veridra account.</p>{notice}<form method='post' action='/forgot-password'><label for='email'>Email</label><input id='email' name='email' type='email' maxlength='254' autocomplete='email' required><button type='submit'>Send reset instructions</button></form><div class='links'><a href='/login'>Back to sign in</a></div></section>",
    )


def _reset_form(token: str, error: str = "") -> HTMLResponse:
    notice = f"<div class='error' role='alert'>{html.escape(error)}</div>" if error else ""
    token_value = html.escape(token, quote=True)
    return _page(
        "Choose a new Veridra password",
        f"<section><h1>Choose a new password</h1><p class='muted'>Use at least 12 characters.</p>{notice}<form method='post' action='/reset-password'><input type='hidden' name='token' value='{token_value}'><label for='new_password'>New password</label><input id='new_password' name='new_password' type='password' minlength='12' maxlength='1024' autocomplete='new-password' required><label for='password_confirm'>Repeat new password</label><input id='password_confirm' name='password_confirm' type='password' minlength='12' maxlength='1024' autocomplete='new-password' required><button type='submit'>Update password</button></form></section>",
    )


@router.get("/login", response_class=HTMLResponse)
def login_page(reset: str = "") -> HTMLResponse:
    return _login_form(reset_complete=reset == "complete")


@router.post("/login", response_model=None)
async def login_submit(request: Request) -> HTMLResponse | RedirectResponse:
    _trusted_origin(request)
    values = _values(await request.body())
    tenant_slug = _one(values, "tenant_slug")
    email = _one(values, "email").lower()
    password = values.get("password", [""])[0]
    authenticator, lifecycle, throttle = _services(request)
    now = datetime.now(UTC)
    decision = throttle.check(email=email, tenant_slug=tenant_slug, now=now)
    if not decision.allowed:
        response = _login_form("Too many login attempts. Try again later.")
        response.status_code = 429
        response.headers["Retry-After"] = str(decision.retry_after_seconds)
        return response
    records = authenticator.authenticate(
        email=email,
        tenant_slug=tenant_slug,
        password=password,
    )
    if records is None:
        failure = throttle.record_failure(email=email, tenant_slug=tenant_slug, now=now)
        if not failure.allowed:
            response = _login_form("Too many login attempts. Try again later.")
            response.status_code = 429
            response.headers["Retry-After"] = str(failure.retry_after_seconds)
            return response
        response = _login_form("Invalid login credentials.")
        response.status_code = 401
        return response
    throttle.clear(email=email, tenant_slug=tenant_slug)
    lifetime = timedelta(hours=8)
    issued = lifecycle.issue(
        user_id=records.user.id,
        tenant_id=records.tenant.id,
        lifetime=lifetime,
    )
    response = RedirectResponse("/agency", status_code=303)
    set_session_cookie(response, issued.credential, max_age=int(lifetime.total_seconds()))
    return response


@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page() -> HTMLResponse:
    return _forgot_form()


@router.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password_submit(request: Request) -> HTMLResponse:
    _trusted_origin(request)
    email = _one(_values(await request.body()), "email").lower()
    issued = SQLitePasswordRecoveryService(_database(request)).issue(email=email)
    if issued is not None:
        delivery = getattr(request.app.state, "veridra_password_reset_delivery", None)
        if callable(delivery):
            adapter: PasswordResetDeliveryAdapter = delivery
            adapter(
                PasswordResetDelivery(
                    email=issued.email,
                    token=issued.token,
                    expires_at=issued.expires_at,
                )
            )
    return _forgot_form(submitted=True)


@router.get("/reset-password", response_class=HTMLResponse)
def reset_password_page(token: str = "") -> HTMLResponse:
    if not token or len(token) > 512:
        response = _page(
            "Invalid password reset",
            "<section><h1>Reset link is invalid</h1><p class='muted'>Request a new password reset email.</p><div class='links'><a href='/forgot-password'>Request another reset</a></div></section>",
        )
        response.status_code = 400
        return response
    return _reset_form(token)


@router.post("/reset-password", response_model=None)
async def reset_password_submit(request: Request) -> HTMLResponse | RedirectResponse:
    _trusted_origin(request)
    values = _values(await request.body())
    token = _one(values, "token")
    new_password = values.get("new_password", [""])[0]
    confirmation = values.get("password_confirm", [""])[0]
    if new_password != confirmation:
        response = _reset_form(token, "Passwords do not match.")
        response.status_code = 400
        return response
    if len(new_password) < 12 or len(new_password) > 1024:
        response = _reset_form(token, "Password must contain between 12 and 1024 characters.")
        response.status_code = 400
        return response
    try:
        SQLitePasswordRecoveryService(_database(request)).reset_password(
            token=token,
            new_password=new_password,
        )
    except (PasswordRecoveryError, ValueError):
        response = _page(
            "Invalid password reset",
            "<section><h1>Reset link is invalid or expired</h1><p class='muted'>Request a new password reset email.</p><div class='links'><a href='/forgot-password'>Request another reset</a></div></section>",
        )
        response.status_code = 400
        return response
    return RedirectResponse("/login?reset=complete", status_code=303)
