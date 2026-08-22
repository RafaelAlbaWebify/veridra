from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .atomic_fs_lock import AtomicFileLockError, exclusive_directory_lock
from .identity_tenancy import RequestIdentity
from .prospect import Prospect, prospect_identifier
from .tenant_project_store import default_tenant_data_directory
from .tenant_prospect_store import TenantProspectStore, TenantProspectStoreError


class DiscoveryIngestAction(StrEnum):
    created = "created"
    enriched = "enriched"
    unchanged = "unchanged"


@dataclass(frozen=True, slots=True)
class DiscoveryIngestItem:
    prospect_id: str
    action: DiscoveryIngestAction


class DiscoveryIngestError(RuntimeError):
    pass


def _append_evidence(existing: str, observed: str) -> str:
    current = existing.strip()
    incoming = observed.strip()
    if not incoming or incoming in current:
        return current
    combined = f"{current}\n\n{incoming}" if current else incoming
    return combined[-4000:]


def merge_discovery_prospect(existing: Prospect, observed: Prospect) -> Prospect:
    """Merge machine-observed discovery data without replacing human workflow state."""

    if prospect_identifier(existing) != prospect_identifier(observed):
        raise ValueError("Discovery observations must resolve to the same prospect identity.")

    updates: dict[str, object] = {
        "sector": existing.sector or observed.sector,
        "administrative_area": existing.administrative_area or observed.administrative_area,
        "phone": existing.phone or observed.phone,
        "source_url": existing.source_url or observed.source_url,
        "evidence_summary": _append_evidence(
            existing.evidence_summary,
            observed.evidence_summary,
        ),
    }
    changed = any(getattr(existing, field) != value for field, value in updates.items())
    if not changed:
        return existing

    updates["updated_at"] = max(existing.updated_at, observed.updated_at)
    return Prospect.model_validate(
        {
            **existing.model_dump(mode="json"),
            **updates,
        }
    )


class TenantProspectDiscoveryIngestor:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_tenant_data_directory()
        self.store = TenantProspectStore(self.root)

    def ingest(
        self,
        identity: RequestIdentity,
        prospects: Sequence[Prospect],
    ) -> tuple[DiscoveryIngestItem, ...]:
        outcomes: list[DiscoveryIngestItem] = []
        lock_path = self.root / identity.tenant_id / ".prospect-ingest.lock"
        try:
            with exclusive_directory_lock(lock_path):
                for observed in prospects:
                    prospect_id = prospect_identifier(observed)
                    target = self.store.ref(identity, prospect_id)
                    try:
                        existing = self.store.load(identity, target)
                    except TenantProspectStoreError:
                        self.store.save(identity, observed)
                        outcomes.append(
                            DiscoveryIngestItem(prospect_id, DiscoveryIngestAction.created)
                        )
                        continue

                    merged = merge_discovery_prospect(existing, observed)
                    if merged == existing:
                        outcomes.append(
                            DiscoveryIngestItem(prospect_id, DiscoveryIngestAction.unchanged)
                        )
                        continue
                    self.store.replace(identity, target, merged)
                    outcomes.append(
                        DiscoveryIngestItem(prospect_id, DiscoveryIngestAction.enriched)
                    )
        except AtomicFileLockError as exc:
            raise DiscoveryIngestError("Prospect ingest is already active.") from exc
        return tuple(outcomes)
