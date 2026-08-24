from __future__ import annotations

import argparse
import csv
import io
import json
import zipfile
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .core import Assessment, Status
from .exports import build_evidence_package
from .service import assess_url

_TRACKING_KEYS = {
    "fbclid",
    "gad_source",
    "gclid",
    "gbraid",
    "wbraid",
    "y_source",
}
_SEVERITY_WEIGHTS = {
    "critical": 8,
    "high": 5,
    "medium": 3,
    "low": 1,
    "info": 0,
}


@dataclass(frozen=True, slots=True)
class AuditTarget:
    result_rank: int
    name: str
    source_url: str
    captured_website: str
    audit_url: str
    provider_key: str


@dataclass(frozen=True, slots=True)
class AuditOutcome:
    target: AuditTarget
    assessment: Assessment | None
    error: str = ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="veridra-prospect-audit-evidence")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--output-directory", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--max-targets", type=int, default=20)
    return parser


def _is_tracking_key(key: str) -> bool:
    folded = key.casefold()
    return folded.startswith("utm_") or folded in _TRACKING_KEYS


def canonicalize_audit_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Captured website must be an HTTP or HTTPS URL with a hostname.")
    filtered_query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not _is_tracking_key(key)
    ]
    hostname = parsed.hostname.casefold()
    port = parsed.port
    if (parsed.scheme.casefold() == "http" and port == 80) or (
        parsed.scheme.casefold() == "https" and port == 443
    ):
        port = None
    netloc = hostname if port is None else f"{hostname}:{port}"
    path = parsed.path or "/"
    return urlunsplit(
        (
            parsed.scheme.casefold(),
            netloc,
            path,
            urlencode(filtered_query, doseq=True),
            "",
        )
    )


def _latest_discovery_zip(downloads: Path) -> Path:
    candidates = sorted(
        downloads.glob("VERIDRA_DISCOVERY_*.zip"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(
            f"No VERIDRA_DISCOVERY_*.zip file was found in {downloads}."
        )
    return candidates[0]


def _load_discovery_targets(path: Path, *, max_targets: int) -> list[AuditTarget]:
    if max_targets < 1 or max_targets > 100:
        raise ValueError("max-targets must be between 1 and 100.")
    with zipfile.ZipFile(path) as archive:
        try:
            raw = json.loads(archive.read("captured_observations.json"))
        except KeyError as exc:
            raise ValueError(
                "Discovery ZIP does not contain captured_observations.json."
            ) from exc
    if not isinstance(raw, list):
        raise ValueError("captured_observations.json must contain a list.")

    targets: list[AuditTarget] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        business = row.get("business")
        if not isinstance(business, dict):
            continue
        website = business.get("website")
        if not isinstance(website, str) or not website.strip():
            continue
        name = str(business.get("name", "")).strip()
        provider_key = str(business.get("provider_key", "")).strip()
        source_url = str(business.get("source_url", "")).strip()
        try:
            result_rank = int(row.get("result_rank", len(targets) + 1))
            audit_url = canonicalize_audit_url(website)
        except (TypeError, ValueError):
            continue
        targets.append(
            AuditTarget(
                result_rank=result_rank,
                name=name or audit_url,
                source_url=source_url,
                captured_website=website,
                audit_url=audit_url,
                provider_key=provider_key,
            )
        )
        if len(targets) >= max_targets:
            break
    if not targets:
        raise ValueError("Discovery ZIP contains no auditable captured websites.")
    return targets


def technical_opportunity_score(assessment: Assessment) -> int:
    return sum(
        _SEVERITY_WEIGHTS.get(finding.severity.casefold(), 0)
        for finding in assessment.findings
        if finding.status == Status.attention
    )


def _shared_host_counts(targets: Sequence[AuditTarget]) -> Counter[str]:
    return Counter((urlsplit(item.audit_url).hostname or "").casefold() for item in targets)


def _score_for_sort(row: dict[str, object]) -> int:
    value = row["technical_opportunity_score"]
    return int(value) if value is not None else -1


def _ranking_rows(outcomes: Sequence[AuditOutcome]) -> list[dict[str, object]]:
    host_counts = _shared_host_counts([item.target for item in outcomes])
    rows: list[dict[str, object]] = []
    for outcome in outcomes:
        target = outcome.target
        hostname = (urlsplit(target.audit_url).hostname or "").casefold()
        assessment = outcome.assessment
        attention = 0
        unavailable = 0
        score: int | None = None
        total = 0
        if assessment is not None:
            attention = assessment.summary.get("attention", 0)
            unavailable = assessment.summary.get("unavailable", 0)
            total = assessment.summary.get("total", 0)
            score = technical_opportunity_score(assessment)
        rows.append(
            {
                "result_rank": target.result_rank,
                "name": target.name,
                "captured_website": target.captured_website,
                "audit_url": target.audit_url,
                "hostname": hostname,
                "shared_hostname_count": host_counts[hostname],
                "shared_hostname": host_counts[hostname] > 1,
                "technical_opportunity_score": score,
                "attention_findings": attention,
                "unavailable_findings": unavailable,
                "total_findings": total,
                "audit_status": "success" if assessment is not None else "failed",
                "error": outcome.error,
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["audit_status"] != "success",
            -_score_for_sort(row),
            int(row["result_rank"]),
        ),
    )


def _csv_bytes(rows: Sequence[dict[str, object]]) -> bytes:
    buffer = io.StringIO(newline="")
    fieldnames = [
        "result_rank",
        "name",
        "captured_website",
        "audit_url",
        "hostname",
        "shared_hostname_count",
        "shared_hostname",
        "technical_opportunity_score",
        "attention_findings",
        "unavailable_findings",
        "total_findings",
        "audit_status",
        "error",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")


def _safe_name(value: str) -> str:
    clean = "".join(character if character.isalnum() else "-" for character in value)
    return "-".join(part for part in clean.split("-") if part)[:80] or "prospect"


def _build_archive(
    *,
    source_path: Path,
    outcomes: Sequence[AuditOutcome],
    generated_at: str,
) -> bytes:
    ranking = _ranking_rows(outcomes)
    failures = [row for row in ranking if row["audit_status"] == "failed"]
    successes = [outcome for outcome in outcomes if outcome.assessment is not None]
    manifest = {
        "schema_version": 1,
        "generated_at": generated_at,
        "source_discovery_zip": source_path.name,
        "targets": len(outcomes),
        "audit_successes": len(successes),
        "audit_failures": len(failures),
        "persistence": "none",
        "score_model": {
            "name": "technical_opportunity_v1",
            "scope": "observable attention findings only; not commercial propensity",
            "severity_weights": _SEVERITY_WEIGHTS,
            "unavailable_findings_scored": False,
        },
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", _json_bytes(manifest))
        archive.writestr("audit_ranking.json", _json_bytes(ranking))
        archive.writestr("audit_summary.csv", _csv_bytes(ranking))
        archive.writestr("failures.json", _json_bytes(failures))
        archive.writestr(
            "README.md",
            b"# VERIDRA prospect audit evidence\n\n"
            b"Read-only batch audit generated from discovery evidence.\n\n"
            b"`technical_opportunity_score` ranks observable VERIDRA attention findings by "
            b"severity. It does **not** estimate willingness to buy, business size, budget, "
            b"or expected conversion. `unavailable` findings do not add points.\n",
        )
        for outcome in successes:
            assessment = outcome.assessment
            assert assessment is not None
            package = build_evidence_package(assessment)
            stem = f"{outcome.target.result_rank:02d}-{_safe_name(outcome.target.name)}"
            archive.writestr(
                f"assessments/{stem}.json",
                _json_bytes(assessment.model_dump(mode="json")),
            )
            archive.writestr(f"evidence/{stem}.zip", package.content)
    return buffer.getvalue()


def run_batch(
    targets: Sequence[AuditTarget],
    *,
    assessor: Callable[[str], Assessment] = assess_url,
) -> list[AuditOutcome]:
    outcomes: list[AuditOutcome] = []
    for index, target in enumerate(targets, start=1):
        print(f"[Veridra] Auditing {index}/{len(targets)}: {target.name} -> {target.audit_url}")
        try:
            assessment = assessor(target.audit_url)
        except Exception as exc:
            outcomes.append(AuditOutcome(target=target, assessment=None, error=str(exc)))
            print(f"[Veridra] Audit failed for {target.name}: {exc}")
            continue
        outcomes.append(AuditOutcome(target=target, assessment=assessment))
    return outcomes


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    input_path = args.input or _latest_discovery_zip(args.downloads)
    targets = _load_discovery_targets(input_path, max_targets=args.max_targets)
    outcomes = run_batch(targets)
    generated_at = datetime.now(UTC).isoformat()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    args.output_directory.mkdir(parents=True, exist_ok=True)
    output_path = args.output_directory / f"VERIDRA_PROSPECT_AUDITS_{stamp}.zip"
    output_path.write_bytes(
        _build_archive(
            source_path=input_path,
            outcomes=outcomes,
            generated_at=generated_at,
        )
    )
    successes = sum(1 for item in outcomes if item.assessment is not None)
    print(
        json.dumps(
            {
                "input": str(input_path),
                "output": str(output_path),
                "targets": len(outcomes),
                "audit_successes": successes,
                "audit_failures": len(outcomes) - successes,
                "persistence": "none",
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if successes else 2


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
