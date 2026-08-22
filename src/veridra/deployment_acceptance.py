from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse

import httpx

from .core import UnsafeTargetError, resolve_public_ips

_TIMEOUT_SECONDS = 10.0


class DeploymentAcceptanceError(RuntimeError):
    pass


class DeploymentCheckStatus(StrEnum):
    ok = "ok"
    critical = "critical"


@dataclass(frozen=True)
class DeploymentCheck:
    name: str
    status: DeploymentCheckStatus
    message: str


@dataclass(frozen=True)
class DeploymentAcceptanceResult:
    status: DeploymentCheckStatus
    checks: tuple[DeploymentCheck, ...]

    @property
    def ready(self) -> bool:
        return self.status is DeploymentCheckStatus.ok

    @property
    def exit_code(self) -> int:
        return 0 if self.ready else 2

    def as_dict(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "status": self.status.value,
            "checks": [
                {
                    "name": check.name,
                    "status": check.status.value,
                    "message": check.message,
                }
                for check in self.checks
            ],
        }


@dataclass(frozen=True)
class ValidatedDeploymentOrigin:
    origin: str
    hostname: str
    public_ips: tuple[str, ...]


def _validated_origin(origin: str) -> ValidatedDeploymentOrigin:
    value = origin.strip().rstrip("/")
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise DeploymentAcceptanceError(
            "Deployment origin must be a bare HTTPS origin without credentials, path or query."
        )
    try:
        public_ips = tuple(resolve_public_ips(parsed.hostname))
    except UnsafeTargetError as exc:
        raise DeploymentAcceptanceError(
            "Deployment origin must resolve only to public network addresses."
        ) from exc
    if not public_ips:
        raise DeploymentAcceptanceError(
            "Deployment origin did not resolve to a public network address."
        )
    return ValidatedDeploymentOrigin(
        origin=value,
        hostname=parsed.hostname,
        public_ips=public_ips,
    )


def _pin_deployment_request(
    request: httpx.Request,
    *,
    hostname: str,
    ip_address: str,
) -> httpx.Request:
    if request.url.host != hostname:
        raise DeploymentAcceptanceError(
            "Deployment request hostname changed before connection."
        )
    request.extensions["sni_hostname"] = hostname
    request.url = request.url.copy_with(host=ip_address)
    return request


class _PinnedDeploymentTransport(httpx.HTTPTransport):
    def __init__(self, *, hostname: str, ip_address: str) -> None:
        super().__init__()
        self.hostname = hostname
        self.ip_address = ip_address

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        pinned = _pin_deployment_request(
            request,
            hostname=self.hostname,
            ip_address=self.ip_address,
        )
        return super().handle_request(pinned)


def _check(
    name: str,
    condition: bool,
    *,
    ok: str,
    failure: str,
) -> DeploymentCheck:
    return DeploymentCheck(
        name=name,
        status=(DeploymentCheckStatus.ok if condition else DeploymentCheckStatus.critical),
        message=ok if condition else failure,
    )


def _security_headers(response: httpx.Response) -> bool:
    csp = response.headers.get("content-security-policy", "")
    return (
        response.headers.get("strict-transport-security", "")
        == "max-age=31536000; includeSubDomains"
        and response.headers.get("x-content-type-options", "") == "nosniff"
        and response.headers.get("x-frame-options", "") == "DENY"
        and "object-src 'none'" in csp
        and "base-uri 'self'" in csp
        and "frame-ancestors 'none'" in csp
    )


def _json_status(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return ""
    if not isinstance(payload, dict):
        return ""
    status = payload.get("status")
    return status if isinstance(status, str) else ""


def run_deployment_acceptance(
    origin: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> DeploymentAcceptanceResult:
    try:
        validated = _validated_origin(origin)
    except DeploymentAcceptanceError:
        check = DeploymentCheck(
            name="origin",
            status=DeploymentCheckStatus.critical,
            message="Deployment origin is invalid or not publicly routable.",
        )
        return DeploymentAcceptanceResult(
            status=DeploymentCheckStatus.critical,
            checks=(check,),
        )

    active_transport = transport or _PinnedDeploymentTransport(
        hostname=validated.hostname,
        ip_address=validated.public_ips[0],
    )
    checks: list[DeploymentCheck] = [
        DeploymentCheck(
            name="origin",
            status=DeploymentCheckStatus.ok,
            message="Deployment origin is a validated public HTTPS origin.",
        )
    ]
    try:
        with httpx.Client(
            base_url=validated.origin,
            timeout=_TIMEOUT_SECONDS,
            follow_redirects=False,
            transport=active_transport,
        ) as client:
            live = client.get("/health/live")
            ready = client.get("/health/ready")
            signup = client.get("/signup")
    except (httpx.HTTPError, DeploymentAcceptanceError):
        checks.append(
            DeploymentCheck(
                name="network",
                status=DeploymentCheckStatus.critical,
                message="Deployment endpoints could not be reached safely.",
            )
        )
        return DeploymentAcceptanceResult(
            status=DeploymentCheckStatus.critical,
            checks=tuple(checks),
        )

    checks.append(
        _check(
            "liveness",
            live.status_code == 200 and _json_status(live) == "ok",
            ok="Production liveness endpoint is healthy.",
            failure="Production liveness endpoint is not healthy.",
        )
    )
    checks.append(
        _check(
            "readiness",
            ready.status_code == 200 and _json_status(ready) == "ok",
            ok="Production readiness endpoint is healthy.",
            failure="Production readiness endpoint is not healthy.",
        )
    )
    checks.append(
        _check(
            "signup",
            signup.status_code == 200
            and "Create your Veridra agency workspace" in signup.text,
            ok="Public signup surface is available.",
            failure="Public signup surface is unavailable or unexpected.",
        )
    )
    checks.append(
        _check(
            "security_headers",
            _security_headers(signup),
            ok="Production security headers are present on the public application surface.",
            failure="Required production security headers are missing or unexpected.",
        )
    )
    checks.append(
        _check(
            "cache_control",
            live.headers.get("cache-control", "") == "no-store"
            and ready.headers.get("cache-control", "") == "no-store"
            and signup.headers.get("cache-control", "") == "no-store",
            ok="Sensitive operational and signup responses are not cacheable.",
            failure="Required no-store cache controls are missing.",
        )
    )
    status = (
        DeploymentCheckStatus.ok
        if all(check.status is DeploymentCheckStatus.ok for check in checks)
        else DeploymentCheckStatus.critical
    )
    return DeploymentAcceptanceResult(status=status, checks=tuple(checks))
