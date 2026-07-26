from __future__ import annotations

import pytest
from fastapi import Request

from veridra.session_cookie import (
    SecureSessionCookieExtractor,
    SessionCookieConfigurationError,
)


def _request(*, cookie: str | None = None, headers: dict[str, str] | None = None) -> Request:
    raw_headers = [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()]
    if cookie is not None:
        raw_headers.append((b"cookie", cookie.encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": raw_headers,
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("testclient", 123),
            "scheme": "http",
        }
    )


@pytest.mark.asyncio
async def test_extracts_only_configured_opaque_cookie() -> None:
    extractor = SecureSessionCookieExtractor()
    credential = "a" * 40

    assert await extractor.extract(_request(cookie=f"veridra_session={credential}")) == credential


@pytest.mark.asyncio
async def test_missing_malformed_and_oversized_cookie_fail_closed() -> None:
    extractor = SecureSessionCookieExtractor()

    assert await extractor.extract(_request()) is None
    assert await extractor.extract(_request(cookie="veridra_session=short")) is None
    assert await extractor.extract(_request(cookie="veridra_session=bad value")) is None
    assert await extractor.extract(_request(cookie=f"veridra_session={'a' * 257}")) is None


@pytest.mark.asyncio
async def test_ignores_authorization_and_identity_headers() -> None:
    extractor = SecureSessionCookieExtractor()
    credential = "b" * 40
    request = _request(
        headers={
            "authorization": f"Bearer {credential}",
            "x-user-id": "a" * 24,
            "x-tenant-id": "b" * 24,
            "x-role": "owner",
        }
    )

    assert await extractor.extract(request) is None


def test_cookie_name_configuration_is_strict() -> None:
    assert SecureSessionCookieExtractor("custom_session").cookie_name == "custom_session"

    with pytest.raises(SessionCookieConfigurationError, match="invalid"):
        SecureSessionCookieExtractor("bad cookie name")
