from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from fastapi import Request
from pydantic import BaseModel, ConfigDict

from .identity_tenancy import (
    AuthenticatedUser,
    AuthSession,
    IdentityBoundaryError,
    RequestIdentity,
    Tenant,
    TenantMembership,
    build_request_identity,
)


class SessionCredentialExtractor(Protocol):
    """Extract an opaque session credential without interpreting identity claims."""

    async def extract(self, request: Request) -> str | None: ...


class IdentityRecordStore(Protocol):
    """Load current server-side identity records for an opaque credential."""

    async def load_by_credential(self, credential: str) -> IdentityRecordSet | None: ...


class IdentityRecordSet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    user: AuthenticatedUser
    tenant: Tenant
    membership: TenantMembership
    session: AuthSession


class ServerSideSessionIdentityAdapter:
    """Resolve requests from opaque credentials and current server-side records.

    The extractor owns transport details such as secure cookies or bearer tokens.
    The store owns credential verification and durable record lookup. This adapter
    trusts neither client identity claims nor cached request roles; it rebuilds the
    request identity from current records on every successful resolution.
    """

    def __init__(
        self,
        *,
        extractor: SessionCredentialExtractor,
        store: IdentityRecordStore,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.extractor = extractor
        self.store = store
        self.clock = clock or (lambda: datetime.now(UTC))

    async def resolve(self, request: Request) -> RequestIdentity | None:
        credential = await self.extractor.extract(request)
        if not credential:
            return None

        records = await self.store.load_by_credential(credential)
        if records is None:
            return None

        try:
            return build_request_identity(
                user=records.user,
                tenant=records.tenant,
                membership=records.membership,
                session=records.session,
                now=self.clock(),
            )
        except IdentityBoundaryError:
            return None
