from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from .core import Assessment, Finding


class HistoryError(RuntimeError):
    pass


@dataclass(frozen=True)
class HistoryEntry:
    id: str
    target: str
    generated_at: str
    mode: str
    total_findings: int


@dataclass(frozen=True)
class Comparison:
    before_id: str
    after_id: str
    added: tuple[str, ...]
    resolved: tuple[str, ...]
    changed: tuple[str, ...]
    unchanged: tuple[str, ...]


def default_history_directory() -> Path:
    configured = os.environ.get("VERIDRA_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve() / "history"
    return Path.home() / ".veridra" / "history"


def _canonical_bytes(assessment: Assessment) -> bytes:
    payload = assessment.model_dump(mode="json")
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def assessment_id(assessment: Assessment) -> str:
    return hashlib.sha256(_canonical_bytes(assessment)).hexdigest()[:24]


def _finding_signature(finding: Finding) -> str:
    payload = finding.model_dump(mode="json")
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


class HistoryStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or default_history_directory()

    def _path(self, entry_id: str) -> Path:
        valid = len(entry_id) == 24 and all(
            char in "0123456789abcdef" for char in entry_id
        )
        if not valid:
            raise HistoryError("Invalid assessment identifier.")
        return self.directory / f"{entry_id}.json"

    def save(self, assessment: Assessment) -> str:
        self.directory.mkdir(parents=True, exist_ok=True)
        entry_id = assessment_id(assessment)
        destination = self._path(entry_id)
        content = _canonical_bytes(assessment)
        if destination.exists():
            return entry_id
        with NamedTemporaryFile(
            mode="wb",
            dir=self.directory,
            prefix=f".{entry_id}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        temporary_path.replace(destination)
        return entry_id

    def load(self, entry_id: str) -> Assessment:
        path = self._path(entry_id)
        try:
            return Assessment.model_validate_json(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise HistoryError("Saved assessment was not found.") from exc
        except (OSError, ValueError) as exc:
            raise HistoryError("Saved assessment could not be read safely.") from exc

    def list(self) -> list[HistoryEntry]:
        if not self.directory.exists():
            return []
        entries: list[HistoryEntry] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                assessment = Assessment.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                continue
            entries.append(
                HistoryEntry(
                    id=path.stem,
                    target=str(assessment.target),
                    generated_at=assessment.generated_at.isoformat(),
                    mode=assessment.mode,
                    total_findings=assessment.summary["total"],
                )
            )
        return sorted(
            entries,
            key=lambda item: (item.generated_at, item.id),
            reverse=True,
        )

    def delete(self, entry_id: str) -> None:
        path = self._path(entry_id)
        try:
            path.unlink()
        except FileNotFoundError as exc:
            raise HistoryError("Saved assessment was not found.") from exc

    def prune(self, keep: int) -> tuple[str, ...]:
        if keep < 0:
            raise HistoryError("Retention count cannot be negative.")
        entries = self.list()
        removed: list[str] = []
        for entry in entries[keep:]:
            self.delete(entry.id)
            removed.append(entry.id)
        return tuple(removed)

    def compare(self, before_id: str, after_id: str) -> Comparison:
        before = self.load(before_id)
        after = self.load(after_id)
        before_map = {item.id: item for item in before.findings}
        after_map = {item.id: item for item in after.findings}
        before_ids = set(before_map)
        after_ids = set(after_map)
        common = before_ids & after_ids
        changed = sorted(
            identifier
            for identifier in common
            if _finding_signature(before_map[identifier])
            != _finding_signature(after_map[identifier])
        )
        unchanged = sorted(common - set(changed))
        return Comparison(
            before_id=before_id,
            after_id=after_id,
            added=tuple(sorted(after_ids - before_ids)),
            resolved=tuple(sorted(before_ids - after_ids)),
            changed=tuple(changed),
            unchanged=tuple(unchanged),
        )
