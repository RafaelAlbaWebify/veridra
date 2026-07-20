from __future__ import annotations

from typing import Any

import pytest

from veridra import collector
from veridra.collector import (
    CollectionError,
    PreparedTarget,
    collect_page,
    prepare_target,
)
from veridra.core import UnsafeTargetError


def test_prepare_target_uses_validated_ip_and_original_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        collector,
        "resolve_public_ips",
        lambda hostname: ["93.184.216.34"],
    )
    target = prepare_target("https://example.com/path?q=1")
    assert target.connect_ip == "93.184.216.34"
    assert target.host_header == "example.com"
    assert target.request_target == "/path?q=1"


def test_https_connection_preserves_original_sni(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: dict[str, Any] = {}

    class FakeContext:
        def wrap_socket(
            self,
            sock: object,
            *,
            server_hostname: str,
        ) -> object:
            recorded["socket"] = sock
            recorded["server_hostname"] = server_hostname
            return object()

    raw_socket = object()
    monkeypatch.setattr(
        "veridra.collector.socket.create_connection",
        lambda *args, **kwargs: raw_socket,
    )

    connection = collector._PinnedHTTPSConnection(
        "example.com",
        "93.184.216.34",
        443,
        5.0,
    )
    setattr(connection, "_ssl_context", FakeContext())
    connection.connect()
    assert recorded == {
        "socket": raw_socket,
        "server_hostname": "example.com",
    }


def test_redirect_target_is_revalidated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_resolve(hostname: str) -> list[str]:
        if hostname == "internal.example":
            raise UnsafeTargetError(
                "Non-public target address is not allowed: 127.0.0.1"
            )
        return ["93.184.216.34"]

    monkeypatch.setattr(collector, "resolve_public_ips", fake_resolve)

    def requester(
        target: PreparedTarget,
        timeout: float,
        max_bytes: int,
    ) -> tuple[int, dict[str, str], bytes]:
        del timeout, max_bytes
        assert target.hostname == "example.com"
        return 302, {"location": "https://internal.example/"}, b""

    with pytest.raises(UnsafeTargetError, match="Non-public"):
        collect_page("https://example.com", requester=requester)


def test_redirect_limit_is_enforced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        collector,
        "resolve_public_ips",
        lambda hostname: ["93.184.216.34"],
    )

    def requester(
        target: PreparedTarget,
        timeout: float,
        max_bytes: int,
    ) -> tuple[int, dict[str, str], bytes]:
        del target, timeout, max_bytes
        return 302, {"location": "/again"}, b""

    with pytest.raises(CollectionError, match="Redirect limit"):
        collect_page(
            "https://example.com",
            requester=requester,
            max_redirects=1,
        )


def test_streaming_response_limit_is_enforced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        status = 200

        def read(self, amount: int) -> bytes:
            return b"x" * amount

        def getheaders(self) -> list[tuple[str, str]]:
            return []

    class FakeConnection:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def request(self, *args: object, **kwargs: object) -> None:
            pass

        def getresponse(self) -> FakeResponse:
            return FakeResponse()

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "veridra.collector.http.client.HTTPConnection",
        FakeConnection,
    )
    target = PreparedTarget(
        url="http://example.com/",
        scheme="http",
        hostname="example.com",
        port=80,
        request_target="/",
        host_header="example.com",
        validated_ips=("93.184.216.34",),
        connect_ip="93.184.216.34",
    )

    with pytest.raises(CollectionError, match="byte limit"):
        collector._request_once(target, timeout=5.0, max_bytes=10)
