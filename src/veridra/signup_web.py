# ruff: noqa: E501
from __future__ import annotations

import html
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from .identity_email_delivery import TenantSignupDelivery, TenantSignupEmailAdapter
from .runtime_config import RuntimeConfig
from .runtime_legal import LegalLinks
from .same_origin import SameOriginRequestError, TrustedSameOriginPolicy
from .session_api import set_session_cookie
from .session_lifecycle import SessionLifecycleService
from .signup_legal_evidence import (
    SQLiteSignupLegalEvidenceStore,
    SignupLegalEvidenceError,
)
from .sqlite_identity_store import SQLiteIdentityRecordStore
from .tenant_signup import (
    SQLiteTenantSignupService,
    TenantSignupError,
    TenantSignupSlugUnavailable,
)

router = APIRouter(tags=["signup"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:760px;margin:48px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:12px;padding:28px}h1{margin-top:0}label{display:block;font-weight:700;margin:14px 0 5px}input{width:100%;padding:11px;border:1px solid #cfd4da;border-radius:7px}input[type=checkbox]{width:auto;padding:0}.legal{margin-top:18px;padding:14px;background:#f4f6f8;border-radius:8px;line-height:1.5}.legal label{display:flex;gap:9px;align-items:flex-start;margin:0 0 8px}.legal p{margin:0}.legal a{font-weight:700}button{margin-top:20px;border:0;border-radius:7px;background:#22272d;color:#fff;padding:11px 16px;cursor:pointer}.muted{color:#68707a}.error{border-left:4px solid #b42318;background:#fff1f0;color:#7a271a;padding:12px;margin-bottom:16px}.success{border-left:4px solid #16794a;background:#f0faf5;padding:12px 14px}
"""

_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


def _page(title: str, body: str, *, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main><section>{body}</section></main></body></html>",
        status_code=status_code,
        headers=_HEADERS,
    )


def _legal_block(legal: LegalLinks | None) -> str:
    if legal is None:
        return ""
    terms = html.escape(legal.terms_url, quote=True)
    privacy = html.escape(legal.privacy_url, quote=True)
    return f"""<div class='legal'><label for='terms_accepted'><input id='terms_accepted' name='terms_accepted' type='checkbox' value='yes' required><span>I agree to the <a href='{terms}' target='_blank' rel='noopener'>Terms of Service</a>.</span></label><p class='muted'>Before creating an account, read the <a href='{privacy}' target='_blank' rel='noopener'>Privacy Notice</a>, which explains how personal data are handled.</p></div>"""


def _signup_form(
    error: str = "",
    *,
    status_code: int = 200,
    legal: LegalLinks | None = None,
) -> HTMLResponse:
    error_html = f"<div class='error' role='alert'>{html.escape(error)}</div>" if error else ""
    body = f"""<h1>Create your Veridra agency workspace</h1><p class='muted'>Start on the Free plan. No payment is created during signup.</p>{error_html}<form method='post' action='/signup'><label for='tenant_name'>Agency or organisation name</label><input id='tenant_name' name='tenant_name' maxlength='160' required><label for='tenant_slug'>Workspace slug</label><input id='tenant_slug' name='tenant_slug' minlength='3' maxlength='80' pattern='[a-z0-9]+(?:-[a-z0-9]+)*' required><label for='owner_name'>Your name</label><input id='owner_name' name='owner_name' maxlength='120' required><label for='owner_email'>Email</label><input id='owner_email' name='owner_email' type='email' maxlength='254' autocomplete='email' required><label for='password'>Password</label><input id='password' name='password' type='password' minlength='12' maxlength='1024' autocomplete='new-password' required><label for='password_confirm'>Repeat password</label><input id='password_confirm' name='password_confirm' type='password' minlength='12' maxlength='1024' autocomplete='new-password' required>{_legal_block(legal)}<button type='submit'>Send verification email</button></form><p class='muted'>Already have an account? <a href='/login'>Sign in</a>.</p>"""
    return _page("Create Veridra workspace", body, status_code=status_code)


def _runtime(request: Request) -> RuntimeConfig:
    value = getattr(request.app.state, "veridra_runtime_config", None)
    if not isinstance(value, RuntimeConfig) or not value.trusted_origin:
        raise HTTPException(status_code=503, detail="Signup is not configured.")
    return value


def _legal(request: Request) -> LegalLinks | None:
    value = getattr(request.app.state, "veridra_legal_links", None)
    return value if isinstance(value, LegalLinks) else None


def _database(request: Request) -> Path:
    value = getattr(request.app.state, "veridra_identity_database", None)
    if not isinstance(value, Path):
        raise HTTPException(status_code=503, detail="Signup is not configured.")
    return value


def _tenant_root(request: Request) -> Path:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    if not isinstance(value, Path):
        raise HTTPException(status_code=503, detail="Signup is not configured.")
    return value


def _identity_store(request: Request) -> SQLiteIdentityRecordStore:
    value = getattr(request.app.state, "veridra_identity_store", None)
    if not isinstance(value, SQLiteIdentityRecordStore):
        raise HTTPException(status_code=503, detail="Signup is not configured.")
    return value


def _delivery(request: Request) -> TenantSignupEmailAdapter:
    value = getattr(request.app.state, "veridra_tenant_signup_delivery", None)
    if not isinstance(value, TenantSignupEmailAdapter):
        raise HTTPException(status_code=503, detail="Signup email is not configured.")
    return value


def _service(request: Request) -> SQLiteTenantSignupService:
    return SQLiteTenantSignupService(_database(request), _tenant_root(request))


def _legal_evidence(request: Request) -> SQLiteSignupLegalEvidenceStore:
    return SQLiteSignupLegalEvidenceStore(_database(request))


def _same_origin(request: Request) -> None:
    try:
        TrustedSameOriginPolicy(_runtime(request).trusted_origin or "").validate(request)
    except SameOriginRequestError as exc:
        raise HTTPException(status_code=403, detail="Signup request is not permitted.") from exc


def _values(body: bytes) -> dict[str, list[str]]:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True)


def _one(values: dict[str, list[str]], name: str) -> str:
    return values.get(name, [""])[0].strip()


def _token(value: str) -> str:
    token = value.strip()
    if not 32 <= len(token) <= 512:
        raise TenantSignupError("Signup verification token is invalid.")
    return token


@router.get("/signup", response_class=HTMLResponse)
def signup(request: Request) -> HTMLResponse:
    _runtime(request)
    _database(request)
    _tenant_root(request)
    _delivery(request)
    return _signup_form(legal=_legal(request))


@router.post("/signup", response_model=None)
async def request_signup(request: Request) -> HTMLResponse:
    _same_origin(request)
    delivery = _delivery(request)
    service = _service(request)
    legal = _legal(request)
    values = _values(await request.body())
    if legal is not None and _one(values, "terms_accepted") != "yes":
        return _signup_form(
            "You must agree to the Terms of Service to create a workspace.",
            status_code=400,
            legal=legal,
        )
    password = values.get("password", [""])[0]
    confirmation = values.get("password_confirm", [""])[0]
    if password != confirmation:
        return _signup_form("Passwords do not match.", status_code=400, legal=legal)
    try:
        issued = await run_in_threadpool(
            service.issue,
            tenant_slug=_one(values, "tenant_slug"),
            tenant_name=_one(values, "tenant_name"),
            owner_email=_one(values, "owner_email"),
            owner_name=_one(values, "owner_name"),
            password=password,
        )
    except TenantSignupSlugUnavailable:
        return _page(
            "Workspace unavailable",
            "<h1>Workspace slug unavailable</h1><p>Choose a different workspace slug and try again.</p><p><a href='/signup'>Back to signup</a></p>",
            status_code=409,
        )
    except (TenantSignupError, ValueError) as exc:
        return _page(
            "Signup error",
            f"<h1>Check your signup details</h1><div class='error'>{html.escape(str(exc))}</div><p><a href='/signup'>Back to signup</a></p>",
            status_code=400,
        )
    if issued is not None:
        if legal is not None:
            try:
                await run_in_threadpool(
                    _legal_evidence(request).record_pending,
                    token=issued.token,
                    tenant_slug=_one(values, "tenant_slug"),
                    owner_email=issued.email,
                    owner_name=_one(values, "owner_name"),
                    terms_url=legal.terms_url,
                    privacy_url=legal.privacy_url,
                )
            except SignupLegalEvidenceError:
                await run_in_threadpool(service.cancel, issued.token)
                return _page(
                    "Signup state unavailable",
                    "<h1>Signup could not be completed safely</h1><p>Try again after the operator restores signup evidence storage.</p>",
                    status_code=503,
                )
        sent = await run_in_threadpool(
            delivery,
            TenantSignupDelivery(
                email=issued.email,
                token=issued.token,
                expires_at=issued.expires_at,
            ),
        )
        if not sent:
            try:
                await run_in_threadpool(service.cancel, issued.token)
                if legal is not None:
                    await run_in_threadpool(_legal_evidence(request).cancel, issued.token)
            except (TenantSignupError, SignupLegalEvidenceError):
                return _page(
                    "Signup state unavailable",
                    "<h1>Signup could not be completed safely</h1><p>Contact the operator before retrying.</p>",
                    status_code=503,
                )
            return _page(
                "Signup email unavailable",
                "<h1>Verification email could not be sent</h1><p>Try signup again after email delivery is restored.</p>",
                status_code=503,
            )
    return _page(
        "Check your email",
        "<h1>Check your email</h1><div class='success'>If these details can be registered, a verification link has been sent. The workspace is not created until that link is confirmed.</div>",
        status_code=202,
    )


@router.get("/verify-signup", response_class=HTMLResponse)
async def verify_signup(request: Request, token: str = "") -> HTMLResponse:
    try:
        checked = _token(token)
    except TenantSignupError:
        return _page(
            "Invalid signup",
            "<h1>Signup link is invalid or expired</h1><p><a href='/signup'>Start again</a>.</p>",
            status_code=400,
        )
    if not await run_in_threadpool(_service(request).is_valid, checked):
        return _page(
            "Invalid signup",
            "<h1>Signup link is invalid or expired</h1><p><a href='/signup'>Start again</a>.</p>",
            status_code=400,
        )
    body = f"""<h1>Confirm agency workspace</h1><p>The email address has received the signup link. Confirm below to create the Veridra workspace.</p><form method='post' action='/verify-signup'><input type='hidden' name='token' value='{html.escape(checked, quote=True)}'><button type='submit'>Create my workspace</button></form>"""
    return _page("Confirm Veridra signup", body)


@router.post("/verify-signup", response_model=None)
async def complete_signup(request: Request) -> HTMLResponse | RedirectResponse:
    _same_origin(request)
    values = _values(await request.body())
    try:
        token = _token(_one(values, "token"))
        accepted = await run_in_threadpool(_service(request).accept, token=token)
    except (TenantSignupError, ValueError):
        return _page(
            "Invalid signup",
            "<h1>Signup link is invalid, expired or no longer available</h1><p><a href='/signup'>Start again</a>.</p>",
            status_code=400,
        )
    try:
        await run_in_threadpool(
            _legal_evidence(request).mark_activated_if_present,
            token=token,
            tenant_id=accepted.tenant_id,
            user_id=accepted.user_id,
        )
    except SignupLegalEvidenceError:
        return _page(
            "Signup evidence unavailable",
            "<h1>Your workspace was created, but signup evidence could not be finalized</h1><p>Contact the operator before continuing.</p>",
            status_code=503,
        )
    lifetime = timedelta(hours=8)
    issued = await run_in_threadpool(
        SessionLifecycleService(_identity_store(request)).issue,
        user_id=accepted.user_id,
        tenant_id=accepted.tenant_id,
        lifetime=lifetime,
    )
    response = RedirectResponse("/agency", status_code=303)
    set_session_cookie(response, issued.credential, max_age=int(lifetime.total_seconds()))
    return response
