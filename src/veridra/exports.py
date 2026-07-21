from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass

from .core import Assessment
from .report_profiles import ReportProfile
from .reports import render_report


@dataclass(frozen=True)
class EvidencePackage:
    filename: str
    content: bytes
    manifest: dict[str, str]


def _json_bytes(assessment: Assessment) -> bytes:
    payload = assessment.model_dump(mode="json")
    return json.dumps(
        payload,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def build_evidence_package(
    assessment: Assessment,
    profile: ReportProfile | None = None,
) -> EvidencePackage:
    assessment_json = _json_bytes(assessment)
    report_html = render_report(assessment, profile=profile).encode("utf-8")
    manifest = {
        "assessment.json": _sha256(assessment_json),
        "report.html": _sha256(report_html),
    }
    manifest_bytes = "".join(
        f"{digest}  {name}\n" for name, digest in sorted(manifest.items())
    ).encode("utf-8")

    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for name, content in (
            ("assessment.json", assessment_json),
            ("report.html", report_html),
            ("manifest.sha256", manifest_bytes),
        ):
            info = zipfile.ZipInfo(name)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)

    target_host = assessment.target.host or "website"
    safe_host = "".join(
        character if character.isalnum() or character in {"-", "."} else "-"
        for character in target_host
    ).strip("-.") or "website"
    filename = f"veridra-{safe_host}-evidence.zip"
    return EvidencePackage(
        filename=filename,
        content=buffer.getvalue(),
        manifest=manifest,
    )
