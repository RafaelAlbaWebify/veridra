from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel, ConfigDict, Field

from .identity_tenancy import RequestIdentity, TenantCapability, require_tenant_capability
from .tenant_project_store import default_tenant_data_directory


class OutreachSuppressionRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    email_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)
    source_prospect_id: str = Field(default="", max_length=24)
    suppressed_at: datetime


def normalized_email_hash(email: str) -> str:
    normalized = email.strip().casefold()
    if not normalized or "@" not in normalized:
        raise ValueError("A valid contact email is required for suppression.")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _atomic_json(path: Path, payload: BaseModel) -> None:
    content = json.dumps(
        payload.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(content)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


class TenantOutreachSuppressionStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_tenant_data_directory()

    def _directory(self, identity: RequestIdentity) -> Path:
        return self.root / identity.tenant_id / "outreach-suppression"

    def is_suppressed(self, identity: RequestIdentity, email: str) -> bool:
        require_tenant_capability(identity, TenantCapability.manage_leads)
        digest = normalized_email_hash(email)
        return (self._directory(identity) / f"{digest}.json").is_file()

    def suppress(
        self,
        identity: RequestIdentity,
        *,
        email: str,
        reason: str,
        source_prospect_id: str = "",
        suppressed_at: datetime | None = None,
    ) -> OutreachSuppressionRecord:
        require_tenant_capability(identity, TenantCapability.manage_leads)
        record = OutreachSuppressionRecord(
            email_hash=normalized_email_hash(email),
            reason=reason,
            source_prospect_id=source_prospect_id,
            suppressed_at=(suppressed_at or datetime.now(UTC)).astimezone(UTC),
        )
        _atomic_json(
            self._directory(identity) / f"{record.email_hash}.json",
            record,
        )
        return record

    def load(
        self,
        identity: RequestIdentity,
        email: str,
    ) -> OutreachSuppressionRecord | None:
        require_tenant_capability(identity, TenantCapability.manage_leads)
        digest = normalized_email_hash(email)
        path = self._directory(identity) / f"{digest}.json"
        if not path.is_file():
            return None
        try:
            return OutreachSuppressionRecord.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return None
