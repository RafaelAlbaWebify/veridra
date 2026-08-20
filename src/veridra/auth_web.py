# ruff: noqa: E501
from __future__ import annotations

import html
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .login_throttle import SQLiteLoginThrottle
from .password_auth import SQLitePasswordAuthenticator
from .session_api import set_session_cookie
from .session_lifecycle import SessionLifecycleService
from .sqlite_identity_store import SQLiteIdentityRecordStore

router = APIRouter(tags=["authentication-web"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:680px;margin:48px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:12px;padding:28px}h1{margin-top:0}label{display:block;font-weight:700;margin:14px 0 5px}input{width:100%;padding:11px;border:1px solid #cfd4da;border-radius:7px}button,.button{display:inline-block;margin-top:20px;border:0;border-radius:7px;background:#22272d;color:#fff;padding:11px 16px;text-decoration:none;cursor:pointer}.muted{color:#68707a}.error{border-left:4px solid #b42318;background:#fff1f0;color:#7a271a;padding:12px;margin-bottom:16px}
"""


def _safe_next(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        return "/agency"
    parsed = urlparse(candidate)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/") or candidate.startswith("//"):
        return "/agency"
    return candidate[:2048]


def _page(
    *,
    error: str | None = None,
    next_url: str = "/agency",
    email: str = "",
    tenant_slug: str = "",
) -> str:
    error_html = f"<div class='error' role='alert'>{html.escape(error)}</div>" if error else ""
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Sign in · Veridra</title><style>{_STYLE}</style></head><body><main><section><h1>Sign in to Veridra</h1><p class='muted'>Use the workspace slug for the tenant you want to enter.</p>{error_html}<form method='post' action='/login'><input type='hidden' name='next' value='{html.escape(_safe_next(next_url), quote=True)}'><label for='email'>Email</label><input id='email' name='email' type='email' maxlength='254' autocomplete='username' value='{html.escape(email, quote=True)}' required><label for='tenant_slug'>Workspace slug</label><input id='tenant_slug' name='tenant_slug' minlength='3' maxlength='80' pattern='[a-z0-9]+(?:-[a-z0-9]+)*' value='{html.escape(tenant_slug, quote=True)}' required><label for='password'>Password</label><input id='password' name='password' type='password' maxlength='1024' autocomplete='current-password' required><button type='submit'>Sign in</button></form></section></main></body></html>"""


def _services(
    request: Request,
) -> tuple[SQLitePasswordAuthenticator, SQLiteIdentityRecordStore, SQLiteLoginThrottle]:
    authenticator = getattr(request.app.state, "veridra_password_authenticator", None)
    identity_store = getattr(request.app.state, "veridra_identity_store", None)
    throttle = getattr(request.app.state, "veridra_login_throttle", None)
    if (
        not isinstance(authenticator, SQLitePasswordAuthenticator)
        or not isinstance(identity_store, SQLiteIdentityRecordStore)
        or not isinstance(throttle, SQLiteLoginThrottle)
    ):
        raise HTTPException(status_code=503, detail="Authentication service is not configured.")
    return authenticator, identity_store, throttle


def _values(body: bytes) -> dict[str, list[str]]:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True)


def _one(values: dict[str, list[str]], name: str) -> str:
    return values.get(name, [""])[0].strip()


@router.get("/login", response_class=HTMLResponse)
def login_page(
    next: str = "/agency",
    email: str = "",
    tenant_slug: str = "",
) -> str:
    return _page(
        next_url=_safe_next(next),
        email=email,
        tenant_slug=tenant_slug,
    )


@router.post("/login", response_model=None)
async def login_submit(request: Request) -> HTMLResponse | RedirectResponse:
    values = _values(await request.body())
    email = _one(values, "email").lower()
    tenant_slug = _one(values, "tenant_slug").lower()
    password = values.get("password", [""])[0]
    next_url = _safe_next(_one(values, "next"))
    authenticator, identity_store, throttle = _services(request)
    decision = throttle.check(email=email, tenant_slug=tenant_slug)
    if not decision.allowed:
        return HTMLResponse(
            _page(
                error="Too many login attempts. Try again later.",
                next_url=next_url,
                email=email,
                tenant_slug=tenant_slug,
            ),
            status_code=429,
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )
    records = authenticator.authenticate(
        email=email,
        tenant_slug=tenant_slug,
        password=password,
    )
    if records is None:
        failure = throttle.record_failure(email=email, tenant_slug=tenant_slug)
        status_code = 429 if not failure.allowed else 401
        error = (
            "Too many login attempts. Try again later."
            if status_code == 429
            else "Invalid login credentials."
        )
        headers = (
            {"Retry-After": str(failure.retry_after_seconds)}
            if status_code == 429
            else None
        )
        return HTMLResponse(
            _page(
                error=error,
                next_url=next_url,
                email=email,
                tenant_slug=tenant_slug,
            ),
            status_code=status_code,
            headers=headers,
        )
    throttle.clear(email=email, tenant_slug=tenant_slug)
    lifetime = timedelta(hours=8)
    issued = SessionLifecycleService(identity_store).issue(
        user_id=records.user.id,
        tenant_id=records.tenant.id,
        lifetime=lifetime,
    )
    response = RedirectResponse(next_url, status_code=303)
    set_session_cookie(response, issued.credential, max_age=int(lifetime.total_seconds()))
    return response
