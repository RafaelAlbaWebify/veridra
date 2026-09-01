from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from .ai_review_exchange import AIReviewBundle, AIReviewResult, ReviewContextType
from .identity_tenancy import (
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)


class TenantAIReviewStoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class AIReviewHistoryEntry:
    review_id: str
    context_type: ReviewContextType
    context_id: str
    generated_at: str
    source_bundle_id: str
    model_provenance: str | None


def default_ai_review_directory() -> Path:
    configured = os.environ.get("VERIDRA_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve() / "tenants"
    return Path.home() / ".veridra" / "tenants"


def _safe_component(value: str) -> str:
    if not value or len(value) > 160:
        raise TenantAIReviewStoreError("Invalid AI review storage identifier.")
    if any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for character in value):
        raise TenantAIReviewStoreError("Invalid AI review storage identifier.")
    return value


class TenantAIReviewStore:
    """Tenant-isolated append-only storage for exported bundles and imported reasoning."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_ai_review_directory()

    def _context_directory(
        self,
        identity: RequestIdentity,
        context_type: ReviewContextType,
        context_id: str,
    ) -> Path:
        return (
            self.root
            / identity.tenant_id
            / "ai-reviews"
            / context_type.value
            / _safe_component(context_id)
        )

    @staticmethod
    def _write_json(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
        with NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.stem}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(encoded)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)

    def save_bundle(self, identity: RequestIdentity, bundle: AIReviewBundle) -> Path:
        require_tenant_capability(identity, TenantCapability.manage_reports)
        directory = self._context_directory(
            identity,
            bundle.context_type,
            bundle.context_id,
        )
        path = directory / "bundles" / f"{bundle.bundle_id}.json"
        if path.exists():
            existing = self.load_bundle(
                identity,
                bundle.context_type,
                bundle.context_id,
                bundle.bundle_id,
            )
            if existing != bundle:
                raise TenantAIReviewStoreError("AI review bundle id collision detected.")
            return path
        self._write_json(path, bundle.model_dump(mode="json"))
        return path

    def load_bundle(
        self,
        identity: RequestIdentity,
        context_type: ReviewContextType,
        context_id: str,
        bundle_id: str,
    ) -> AIReviewBundle:
        require_tenant_capability(identity, TenantCapability.view_data)
        path = (
            self._context_directory(identity, context_type, context_id)
            / "bundles"
            / f"{_safe_component(bundle_id)}.json"
        )
        try:
            return AIReviewBundle.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise TenantAIReviewStoreError("Saved AI review bundle was not found or is invalid.") from exc

    def save_result(
        self,
        identity: RequestIdentity,
        *,
        bundle: AIReviewBundle,
        result: AIReviewResult,
    ) -> Path:
        require_tenant_capability(identity, TenantCapability.manage_reports)
        if result.source_bundle_id != bundle.bundle_id:
            raise TenantAIReviewStoreError("AI review result is not bound to the supplied bundle.")
        directory = self._context_directory(
            identity,
            bundle.context_type,
            bundle.context_id,
        )
        path = directory / "results" / f"{_safe_component(result.review_id)}.json"
        if path.exists():
            existing = self.load_result(
                identity,
                bundle.context_type,
                bundle.context_id,
                result.review_id,
            )
            if existing != result:
                raise TenantAIReviewStoreError("AI review id already exists with different content.")
            return path
        self._write_json(path, result.model_dump(mode="json"))
        return path

    def load_result(
        self,
        identity: RequestIdentity,
        context_type: ReviewContextType,
        context_id: str,
        review_id: str,
    ) -> AIReviewResult:
        require_tenant_capability(identity, TenantCapability.view_data)
        path = (
            self._context_directory(identity, context_type, context_id)
            / "results"
            / f"{_safe_component(review_id)}.json"
        )
        try:
            return AIReviewResult.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise TenantAIReviewStoreError("Saved AI review result was not found or is invalid.") from exc

    def list_results(
        self,
        identity: RequestIdentity,
        context_type: ReviewContextType,
        context_id: str,
    ) -> list[AIReviewHistoryEntry]:
        require_tenant_capability(identity, TenantCapability.view_data)
        directory = self._context_directory(identity, context_type, context_id) / "results"
        if not directory.exists():
            return []
        entries: list[AIReviewHistoryEntry] = []
        for path in directory.glob("*.json"):
            try:
                result = AIReviewResult.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            entries.append(
                AIReviewHistoryEntry(
                    review_id=result.review_id,
                    context_type=context_type,
                    context_id=context_id,
                    generated_at=result.generated_at.isoformat(),
                    source_bundle_id=result.source_bundle_id,
                    model_provenance=result.model_provenance,
                )
            )
        return sorted(entries, key=lambda item: (item.generated_at, item.review_id), reverse=True)
