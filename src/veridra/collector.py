from __future__ import annotations

import http.client
import socket
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse, urlunparse

from .core import UnsafeTargetError, normalize_url, resolve_public_ips

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class CollectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparedTarget:
    url: str
    scheme: str
    hostname: str
    port: int
    request_target: str
    host_header: str
    validated_ips: tuple[str, ...]
    connect_ip: str


@dataclass(frozen=True)
class PageEvidence:
    requested_url: str
    final_url: str
    status_code: int
    headers: dict[str, str]
    body: str
    redirect_chain: tuple[str, ...]
    connected_ip: str
    validated_ips: tuple[str, ...]


@dataclass(frozen=True)
class SiteEvidence:
    homepage: PageEvidence
    robots: PageEvidence | None


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, hostname: str, connect_ip: str, port: int, timeout: float) -> None:
        super().__init__(hostname, port=port, timeout=timeout, context=ssl.create_default_context())
        self._connect_ip = connect_ip

    def connect(self) -> None:
        raw_socket = socket.create_connection(
            (self._connect_ip, self.port),
            self.timeout,
            self.source_address,
        )
        self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)


def prepare_target(raw_url: str) -> PreparedTarget:
    normalized = normalize_url(raw_url)
    parsed = urlparse(normalized)
    hostname = parsed.hostname
    if hostname is None:
        raise UnsafeTargetError("A target hostname is required.")

    validated_ips = tuple(resolve_public_ips(hostname))
    scheme = parsed.scheme
    port = parsed.port or (443 if scheme == "https" else 80)
    default_port = 443 if scheme == "https" else 80
    host_header = hostname if port == default_port else f"{hostname}:{port}"
    request_target = urlunparse(("", "", parsed.path or "/", parsed.params, parsed.query, ""))
    return PreparedTarget(
        url=normalized,
        scheme=scheme,
        hostname=hostname,
        port=port,
        request_target=request_target,
        host_header=host_header,
        validated_ips=validated_ips,
        connect_ip=validated_ips[0],
    )


def _request_once(target: PreparedTarget, timeout: float, max_bytes: int) -> tuple[int, dict[str, str], bytes]:
    if target.scheme == "https":
        connection: http.client.HTTPConnection = _PinnedHTTPSConnection(
            target.hostname,
            target.connect_ip,
            target.port,
            timeout,
        )
    else:
        connection = http.client.HTTPConnection(target.connect_ip, target.port, timeout=timeout)

    try:
        connection.request(
            "GET",
            target.request_target,
            headers={
                "Host": target.host_header,
                "User-Agent": "Veridra/0.2 (+bounded public website assessment)",
                "Accept": "text/html,text/plain;q=0.9,*/*;q=0.1",
                "Connection": "close",
            },
        )
        response = connection.getresponse()
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise CollectionError(f"Response exceeded the {max_bytes}-byte limit.")
        headers = {key.lower(): value for key, value in response.getheaders()}
        return response.status, headers, body
    except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
        raise CollectionError(f"Request failed for {target.url}: {exc}") from exc
    finally:
        connection.close()


Requester = Callable[[PreparedTarget, float, int], tuple[int, dict[str, str], bytes]]


def collect_page(
    raw_url: str,
    *,
    timeout: float = 10.0,
    max_bytes: int = 1_000_000,
    max_redirects: int = 5,
    requester: Requester = _request_once,
) -> PageEvidence:
    requested_url = normalize_url(raw_url)
    current_url = requested_url
    redirects: list[str] = []

    for redirect_count in range(max_redirects + 1):
        prepared = prepare_target(current_url)
        status, headers, body = requester(prepared, timeout, max_bytes)

        if status in _REDIRECT_STATUSES and "location" in headers:
            if redirect_count >= max_redirects:
                raise CollectionError(f"Redirect limit of {max_redirects} exceeded.")
            current_url = normalize_url(urljoin(current_url, headers["location"]))
            redirects.append(current_url)
            continue

        charset = "utf-8"
        content_type = headers.get("content-type", "")
        if "charset=" in content_type.lower():
            charset = content_type.lower().split("charset=", 1)[1].split(";", 1)[0].strip()
        try:
            decoded = body.decode(charset, errors="replace")
        except LookupError:
            decoded = body.decode("utf-8", errors="replace")

        return PageEvidence(
            requested_url=requested_url,
            final_url=prepared.url,
            status_code=status,
            headers=headers,
            body=decoded,
            redirect_chain=tuple(redirects),
            connected_ip=prepared.connect_ip,
            validated_ips=prepared.validated_ips,
        )

    raise CollectionError("The request did not produce a terminal response.")


def collect_site(raw_url: str, *, requester: Requester = _request_once) -> SiteEvidence:
    homepage = collect_page(raw_url, requester=requester)
    parsed = urlparse(homepage.final_url)
    robots_url = urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))
    try:
        robots = collect_page(robots_url, requester=requester, max_bytes=256_000)
    except (CollectionError, UnsafeTargetError):
        robots = None
    return SiteEvidence(homepage=homepage, robots=robots)
