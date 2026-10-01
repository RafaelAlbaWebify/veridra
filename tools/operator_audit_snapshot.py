from __future__ import annotations

import argparse
import json
import re
import zipfile
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _blank(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _normalized_name(value: str) -> str:
    folded = value.casefold().strip()
    folded = re.sub(r"[^\w\s]", " ", folded)
    return re.sub(r"\s+", " ", folded).strip()


def _collection_name(tenant_root: Path, path: Path) -> str:
    relative = path.relative_to(tenant_root)
    return relative.parts[0] if relative.parts else "root"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _legacy_discovery_signal(evidence_summary: str) -> dict[str, Any] | None:
    pattern = re.compile(
        r"Google Maps discovery query: (?P<query>.+?)\. "
        r"Result rank: (?P<rank>\d+)\. "
        r"Rating: (?P<rating>\S+)\. "
        r"Reviews: (?P<reviews>\S+)\. "
        r"Photo signal: (?P<photos>\S+)\. "
        r"Digital-presence opportunity: (?P<band>[a-z]+) "
        r"\((?P<score>\d+)/100; gap (?P<gap>\d+), activity (?P<activity>\d+)\)\.",
        re.IGNORECASE,
    )
    match = pattern.search(evidence_summary)
    if match is None:
        return None
    return {
        "query_text": match.group("query"),
        "result_rank": int(match.group("rank")),
        "opportunity_score": int(match.group("score")),
        "opportunity_band": match.group("band").lower(),
        "digital_gap_score": int(match.group("gap")),
        "business_activity_score": int(match.group("activity")),
    }


def _infer_sector_from_name(name: str) -> str:
    folded = name.casefold()
    rules = (
        ("commissioner for oaths", "Commissioner for Oaths"),
        ("notary", "Notary public"),
        ("solicitor", "Solicitor"),
        ("law firm", "Law firm"),
        ("dentist", "Dentist"),
        ("dental", "Dentist"),
        ("physio", "Physiotherapist"),
        ("chiropr", "Chiropractor"),
        ("accountant", "Accountant"),
    )
    for token, label in rules:
        if token in folded:
            return label
    return ""


def _prospect_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    status = Counter(str(item.get("status") or "missing") for item in records)
    sectors = Counter(str(item.get("sector") or "Unclassified") for item in records)
    providers = Counter(str(item.get("provider") or "missing") for item in records)

    discovery_bands: Counter[str] = Counter()
    missing_sector = 0
    missing_website = 0
    structured_discovery = 0
    legacy_discovery_recoverable = 0
    missing_discovery = 0
    missing_qualification = 0
    sector_inferable_from_name = 0
    discovery_scores: list[int] = []
    name_index: dict[str, list[str]] = defaultdict(list)
    field_missing: Counter[str] = Counter()

    for item in records:
        if not str(item.get("sector") or "").strip():
            missing_sector += 1
            if _infer_sector_from_name(str(item.get("business_name") or "")):
                sector_inferable_from_name += 1
        if not item.get("website"):
            missing_website += 1
        if item.get("qualification") is None:
            missing_qualification += 1

        discovery = item.get("discovery")
        if isinstance(discovery, dict):
            structured_discovery += 1
        else:
            legacy = _legacy_discovery_signal(str(item.get("evidence_summary") or ""))
            if legacy is not None:
                legacy_discovery_recoverable += 1
                discovery = legacy
            else:
                missing_discovery += 1

        if isinstance(discovery, dict):
            band = str(discovery.get("opportunity_band") or "unknown")
            discovery_bands[band] += 1
            score = discovery.get("opportunity_score")
            if isinstance(score, int):
                discovery_scores.append(score)

        for key, value in item.items():
            if _blank(value):
                field_missing[key] += 1

        name = str(item.get("business_name") or "").strip()
        if name:
            name_index[_normalized_name(name)].append(name)

    duplicates = {
        key: values
        for key, values in sorted(name_index.items())
        if len(values) > 1
    }

    score_stats: dict[str, Any] = {
        "count": len(discovery_scores),
        "min": min(discovery_scores) if discovery_scores else None,
        "max": max(discovery_scores) if discovery_scores else None,
        "average": (
            round(sum(discovery_scores) / len(discovery_scores), 2)
            if discovery_scores
            else None
        ),
    }

    return {
        "count": len(records),
        "status_counts": dict(status.most_common()),
        "sector_counts": dict(sectors.most_common()),
        "provider_counts": dict(providers.most_common()),
        "discovery_band_counts": dict(discovery_bands.most_common()),
        "discovery_score_stats": score_stats,
        "quality": {
            "missing_sector": missing_sector,
            "missing_website": missing_website,
            "structured_discovery": structured_discovery,
            "legacy_discovery_recoverable": legacy_discovery_recoverable,
            "missing_discovery_unrecoverable": missing_discovery,
            "missing_qualification": missing_qualification,
            "sector_inferable_from_name": sector_inferable_from_name,
            "possible_duplicate_name_groups": len(duplicates),
        },
        "possible_duplicate_names": duplicates,
        "field_missing_counts": dict(field_missing.most_common()),
    }


def build_snapshot(tenant_data_root: Path) -> dict[str, Any]:
    root = tenant_data_root.expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Tenant data root does not exist: {root}")

    tenants = [path for path in sorted(root.iterdir()) if path.is_dir()]
    result: dict[str, Any] = {
        "contract": "veridra_operator_audit_snapshot",
        "version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "tenant_data_root": str(root),
        "tenants": {},
    }

    for tenant in tenants:
        inventory: Counter[str] = Counter()
        invalid_json: list[str] = []
        collections: dict[str, list[dict[str, Any]]] = defaultdict(list)
        raw_records: list[dict[str, Any]] = []

        for path in sorted(tenant.rglob("*.json")):
            collection = _collection_name(tenant, path)
            inventory[collection] += 1
            try:
                payload = _read_json(path)
            except (OSError, ValueError, json.JSONDecodeError):
                invalid_json.append(str(path.relative_to(tenant)))
                continue

            record = {
                "collection": collection,
                "path": str(path.relative_to(tenant)),
                "payload": payload,
            }
            raw_records.append(record)
            if isinstance(payload, dict):
                collections[collection].append(payload)

        tenant_summary: dict[str, Any] = {
            "inventory": dict(sorted(inventory.items())),
            "invalid_json": invalid_json,
            "record_count": len(raw_records),
            "records": raw_records,
        }
        prospects = collections.get("prospects", [])
        if prospects:
            tenant_summary["prospects"] = _prospect_summary(prospects)

        result["tenants"][tenant.name] = tenant_summary

    return result


def write_snapshot(snapshot: dict[str, Any], output: Path) -> Path:
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "audit-summary.json",
            json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True),
        )
        for tenant_id, tenant in snapshot.get("tenants", {}).items():
            records = tenant.get("records", [])
            archive.writestr(
                f"tenants/{tenant_id}/records.json",
                json.dumps(records, indent=2, ensure_ascii=False, sort_keys=True),
            )
            if "prospects" in tenant:
                archive.writestr(
                    f"tenants/{tenant_id}/prospect-summary.json",
                    json.dumps(
                        tenant["prospects"],
                        indent=2,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                )
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="veridra-operator-audit-snapshot",
        description="Export a read-only operator-local audit snapshot of VERIDRA tenant JSON data.",
    )
    parser.add_argument("--tenant-data-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    snapshot = build_snapshot(args.tenant_data_root)
    output = write_snapshot(snapshot, args.output)
    print(f"operator_audit_snapshot={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
