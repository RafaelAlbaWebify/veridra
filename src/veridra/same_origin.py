from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlsplit

from starlette.requests import Request

_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_PUBLIC_EMBED_PREFIX = "/embed/audit/"


class SameOriginConfigurationError(RuntimeError):
    pass


class SameOriginRequestError(RuntimeError):
    pass


def _normalized_origin(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SameOriginConfigurationError("Trusted origin must be an absolute HTTP(S) URL.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SameOriginConfigurationError("Trusted origin cannot contain credentials or metadata.")
    if parsed.path not in {"", "/"}:
        raise SameOriginConfigurationError("Trusted origin cannot contain a path.")
    default_port = 443 if parsed.scheme == "https" else 80
    port = parsed.port or default_port
    suffix = "" if port == default_port else f":{port}"
    return f"{parsed.scheme}://{parsed.hostname.lower()}{suffix}"


def _origin_from_referer(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SameOriginRequestError("Authenticated request origin is not permitted.")
    default_port = 443 if parsed.scheme == "https" else 80
    port = parsed.port or default_port
    suffix = "" if port == default_port else f":{port}"
    return f"{parsed.scheme}://{parsed.hostname.lower()}{suffix}"


def _is_loopback_origin(value: str) -> bool:
    parsed = urlsplit(value)
    hostname = parsed.hostname
    if hostname is None:
        return False
    if hostname.lower() == "localhost":
        return True
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False


def _request_origin(request: Request) -> str:
    scheme = request.url.scheme
    hostname = request.url.hostname
    if scheme not in {"http", "https"} or not hostname:
        raise SameOriginRequestError("Authenticated request origin is not permitted.")
    default_port = 443 if scheme == "https" else 80
    port = request.url.port or default_port
    suffix = "" if port == default_port else f":{port}"
    return f"{scheme}://{hostname.lower()}{suffix}"


def _loopback_request_matches_trusted_origin(request: Request, trusted_origin: str) -> bool:
    return _is_loopback_origin(trusted_origin) and _request_origin(request) == trusted_origin


@dataclass(frozen=True)
class TrustedSameOriginPolicy:
    trusted_origin: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "trusted_origin", _normalized_origin(self.trusted_origin))

    def requires_validation(self, request: Request) -> bool:
        return (
            request.method.upper() in _UNSAFE_METHODS
            and not request.url.path.startswith(_PUBLIC_EMBED_PREFIX)
        )

    def validate(self, request: Request) -> None:
        if not self.requires_validation(request):
            return
        supplied_origin = request.headers.get("origin")
        if supplied_origin and supplied_origin.strip().lower() != "null":
            try:
                candidate = _normalized_origin(supplied_origin)
            except SameOriginConfigurationError as exc:
                raise SameOriginRequestError(
                    "Authenticated request origin is not permitted."
                ) from exc
        elif supplied_origin and supplied_origin.strip().lower() == "null":
            if not _loopback_request_matches_trusted_origin(request, self.trusted_origin):
                raise SameOriginRequestError(
                    "Authenticated request origin is not permitted."
                )
            candidate = self.trusted_origin
        else:
            referer = request.headers.get("referer")
            if referer:
                candidate = _origin_from_referer(referer)
            elif _loopback_request_matches_trusted_origin(request, self.trusted_origin):
                candidate = self.trusted_origin
            else:
                raise SameOriginRequestError(
                    "Authenticated request origin is not permitted."
                )
        if candidate != self.trusted_origin:
            raise SameOriginRequestError("Authenticated request origin is not permitted.")
