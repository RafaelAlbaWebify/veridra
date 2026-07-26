from __future__ import annotations

import re

from fastapi import Request

_COOKIE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_CREDENTIAL_PATTERN = re.compile(r"^[A-Za-z0-9._~-]{32,256}$")


class SessionCookieConfigurationError(ValueError):
    pass


class SecureSessionCookieExtractor:
    """Extract one opaque session credential from a configured cookie.

    This transport adapter does not parse identity, tenant, role or capability claims.
    It deliberately ignores Authorization and custom identity headers.
    """

    def __init__(self, cookie_name: str = "veridra_session") -> None:
        if not _COOKIE_NAME_PATTERN.fullmatch(cookie_name):
            raise SessionCookieConfigurationError("Session cookie name is invalid.")
        self.cookie_name = cookie_name

    async def extract(self, request: Request) -> str | None:
        credential = request.cookies.get(self.cookie_name)
        if credential is None:
            return None
        if not _CREDENTIAL_PATTERN.fullmatch(credential):
            return None
        return credential
