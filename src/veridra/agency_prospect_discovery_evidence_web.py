from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from .agency_prospect_discovery_web import _REGISTRY, _identity, _prospect_for_ingest

router = APIRouter(
    prefix="/agency/prospects/discover",
    tags=["agency-prospect-discovery-evidence"],
)

_SAFE_FILENAME = re.compile(r"[^a-zA-Z0-9._-]+")


def _safe_filename(value: str) -> str:
    clean = _SAFE_FILENAME.sub("-", value.strip()).strip("-.")
    return clean[:80] or "discovery"


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _summary_markdown(
    *,
    session_id: str,
    query_text: str,
    observations: list[dict[str, object]],
    generated_at: str,
) -> str:
    website_count = sum(1 for row in observations if row["business"].get("website"))  # type: ignore[union-attr]
    lines = [
        "# VERIDRA discovery evidence",
        "",
        f"- Session: `{session_id}`",
        f"- Query: `{query_text}`",
        f"- Generated: `{generated_at}`",
        f"- Captured observations: **{len(observations)}**",
        f"- Website captured: **{website_count}**",
        "",
        "## Captured businesses",
        "",
        "| Rank | Business | Category | Website | Source |",
        "| ---: | --- | --- | --- | --- |",
    ]
    for row in observations:
        business = row["business"]
        if not isinstance(business, dict):
            continue
        values = [
            str(row.get("result_rank", "")),
            str(business.get("name", "")),
            str(business.get("category", "")),
            str(business.get("website") or "not captured"),
            str(business.get("source_url") or "not captured"),
        ]
        escaped = [value.replace("|", "\\|").replace("\n", " ") for value in values]
        lines.append("| " + " | ".join(escaped) + " |")
    lines.extend(
        [
            "",
            "## Audit note",
            "",
            "`captured_observations.json` is the source-of-truth provider output. "
            "`ingest_preview.json` shows the records VERIDRA would prepare for safe ingest; "
            "nothing in this ZIP generation is persisted to the prospect workbench.",
            "",
        ]
    )
    return "\n".join(lines)


def _csv_bytes(observations: list[dict[str, object]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(
        [
            "result_rank",
            "name",
            "category",
            "website",
            "source_url",
            "provider",
            "provider_key",
            "locality",
            "administrative_area",
            "country_code",
            "observed_at",
            "first_seen_scroll_step",
        ]
    )
    for row in observations:
        business = row["business"]
        if not isinstance(business, dict):
            continue
        writer.writerow(
            [
                row.get("result_rank", ""),
                business.get("name", ""),
                business.get("category", ""),
                business.get("website") or "",
                business.get("source_url") or "",
                business.get("provider", ""),
                business.get("provider_key", ""),
                business.get("locality", ""),
                business.get("administrative_area", ""),
                business.get("country_code", ""),
                business.get("observed_at", ""),
                row.get("first_seen_scroll_step", ""),
            ]
        )
    return stream.getvalue().encode("utf-8-sig")


@router.get("/{session_id}/evidence.zip", response_class=Response)
def discovery_evidence_zip(session_id: str, request: Request) -> Response:
    identity = _identity(request)
    try:
        batch = _REGISTRY.snapshot(tenant_id=identity.tenant_id, session_id=session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    snapshot = batch.manager.snapshot()
    if not batch.observations:
        raise HTTPException(status_code=409, detail="Collect discovery results before exporting evidence.")

    generated_at = datetime.now(UTC).isoformat()
    observations = [
        {
            "query_text": item.query_text,
            "query_sequence": item.query_sequence,
            "result_rank": item.result_rank,
            "first_seen_scroll_step": item.first_seen_scroll_step,
            "business": item.business.model_dump(mode="json"),
        }
        for item in batch.observations
    ]
    ingest_preview = [
        {
            "result_rank": item.result_rank,
            "prospect": _prospect_for_ingest(item).model_dump(mode="json"),
        }
        for item in batch.observations
        if item.business.website is not None
    ]
    progress = snapshot.progress
    manifest = {
        "schema_version": 1,
        "generated_at": generated_at,
        "session_id": session_id,
        "query_text": snapshot.query_text,
        "query_sequence": snapshot.query_sequence,
        "state": snapshot.state.value,
        "captured_count": len(observations),
        "website_captured_count": sum(
            1 for row in observations if isinstance(row["business"], dict) and row["business"].get("website")
        ),
        "ingest_preview_count": len(ingest_preview),
        "limits": {
            "max_results": batch.limits.max_results,
            "max_scrolls": batch.limits.max_scrolls,
            "max_elapsed_seconds": batch.limits.max_elapsed_seconds,
            "max_stagnant_scrolls": batch.limits.max_stagnant_scrolls,
        },
        "progress": (
            {
                "scroll_step": progress.scroll_step,
                "unique_results": progress.unique_results,
                "stagnant_scrolls": progress.stagnant_scrolls,
                "elapsed_seconds": progress.elapsed_seconds,
                "stop_reason": progress.stop_reason.value if progress.stop_reason else None,
            }
            if progress is not None
            else None
        ),
        "persistence": "none",
    }

    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", _json_bytes(manifest))
        archive.writestr("captured_observations.json", _json_bytes(observations))
        archive.writestr("captured_businesses.csv", _csv_bytes(observations))
        archive.writestr("ingest_preview.json", _json_bytes(ingest_preview))
        archive.writestr(
            "README.md",
            _summary_markdown(
                session_id=session_id,
                query_text=snapshot.query_text,
                observations=observations,
                generated_at=generated_at,
            ).encode("utf-8"),
        )

    filename = f"VERIDRA_DISCOVERY_{_safe_filename(snapshot.query_text)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    return Response(
        content=archive_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
