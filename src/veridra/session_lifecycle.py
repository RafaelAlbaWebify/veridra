from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .identity_tenancy import AuthSession
from .session_rotation import rotate_session_atomically
from .sqlite_identity_store import SQLiteIdentityRecordStore


@dataclass(frozen=True)
class IssuedSession:
    credential: str
    session: AuthSession


class SessionLifecycleService:
    """Issue and rotate sessions after trusted primary authentication.

    This service deliberately does not verify passwords, OAuth assertions, email links,
    or any other primary credential. Callers must complete that verification first and
    must never reuse a credential supplied by the client.
    """

    def __init__(
        self,
        store: SQLiteIdentityRecordStore,
        *,
        clock: Callable[[], datetime] | None = None,
        credential_factory: Callable[[], str] | None = None,
        session_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.store = store
        self.clock = clock or (lambda: datetime.now(UTC))
        self.credential_factory = credential_factory or (lambda: secrets.token_urlsafe(48))
        self.session_id_factory = session_id_factory or (lambda: secrets.token_urlsafe(32))

    def _build_session(
        self,
        *,
        user_id: str,
        lifetime: timedelta,
    ) -> IssuedSession:
        if lifetime <= timedelta(0):
            raise ValueError("Session lifetime must be positive.")
        issued_at = self.clock().astimezone(UTC)
        credential = self.credential_factory()
        session = AuthSession(
            id=self.session_id_factory(),
            user_id=user_id,
            issued_at=issued_at,
            expires_at=issued_at + lifetime,
        )
        return IssuedSession(credential=credential, session=session)

    def issue(
        self,
        *,
        user_id: str,
        tenant_id: str,
        lifetime: timedelta = timedelta(hours=8),
    ) -> IssuedSession:
        issued = self._build_session(user_id=user_id, lifetime=lifetime)
        self.store.save_session(
            credential=issued.credential,
            tenant_id=tenant_id,
            session=issued.session,
        )
        return issued

    def rotate(
        self,
        *,
        current_session_id: str,
        user_id: str,
        tenant_id: str,
        lifetime: timedelta = timedelta(hours=8),
    ) -> IssuedSession:
        replacement = self._build_session(user_id=user_id, lifetime=lifetime)
        rotate_session_atomically(
            self.store,
            current_session_id=current_session_id,
            replacement_credential=replacement.credential,
            replacement_session=replacement.session,
            tenant_id=tenant_id,
            revoked_at=replacement.session.issued_at,
        )
        return replacement
