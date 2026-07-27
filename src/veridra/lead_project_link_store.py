from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel, ConfigDict, Field


class LeadProjectLinkError(RuntimeError):
    pass


class LeadProjectLink(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    lead_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    project_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    assessment_id: str = Field(pattern=r"^[0-9a-f]{24}$")


class LeadProjectLinkStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, lead_id: str) -> Path:
        if len(lead_id) != 24 or any(char not in "0123456789abcdef" for char in lead_id):
            raise LeadProjectLinkError("Invalid lead identifier.")
        return self.directory / f"{lead_id}.json"

    def load(self, lead_id: str) -> LeadProjectLink | None:
        try:
            return LeadProjectLink.model_validate_json(
                self._path(lead_id).read_text(encoding="utf-8")
            )
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            raise LeadProjectLinkError("Lead project link could not be read safely.") from exc

    def save(self, link: LeadProjectLink) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        destination = self._path(link.lead_id)
        content = json.dumps(
            link.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        with NamedTemporaryFile(
            mode="wb",
            dir=self.directory,
            prefix=f".{link.lead_id}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        temporary_path.replace(destination)
