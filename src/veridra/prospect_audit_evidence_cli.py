from __future__ import annotations

import argparse
import csv
import hashlib
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
    scheme = parsed.scheme.casefold()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Captured website must be an HTTP or HTTPS URL with a hostname.")
    filtered_query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not _is_tracking_key(key)
    ]
    hostname = parsed.hostname.casefold()
    port = parsed.port
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        port = None
    netloc = hostname if port is None else f"{hostname}:{port}"
    path = parsed.path or "/"
    return urlunsplit((scheme, netloc, path, urlencode(filtered_query, doseq=True), ""))


def _latest_discovery_zip(downloads: Path) -> Path:
    candidates = sorted(
        downloads.glob("VERIDRA_DISCOVERY_*.zip"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"No VERIDRA_DISCOVERY_*.zip file was found in {downloads}.")
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


def technical_finding_weight(assessment: Assessment) -> int:
    """Evidence-only sort weight; this is not a commercial propensity score."""
    return sum(
        _SEVERITY_WEIGHTS.get(finding.severity.casefold(), 0)
        for finding in assessment.findings
        if finding.status == Status.attention
    )


def _shared_host_counts(targets: Sequence[AuditTarget]) -> Counter[str]:
    return Counter((urlsplit(item.audit_url).hostname or "").casefold() for item in targets)


def _weight_for_sort(row: dict[str, object]) -> int:
    value = row["technical_finding_weight"]
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
        weight: int | None = None
        total = 0
        if assessment is not None:
            attention = assessment.summary.get("attention", 0)
            unavailable = assessment.summary.get("unavailable", 0)
            total = assessment.summary.get("total", 0)
            weight = technical_finding_weight(assessment)
        rows.append(
            {
                "result_rank": target.result_rank,
                "name": target.name,
                "captured_website": target.captured_website,
                "audit_url": target.audit_url,
                "hostname": hostname,
                "shared_hostname_count": host_counts[hostname],
                "shared_hostname": host_counts[hostname] > 1,
                "technical_finding_weight": weight,
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
            -_weight_for_sort(row),
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
        "technical_finding_weight",
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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique_successes(outcomes: Sequence[AuditOutcome]) -> list[AuditOutcome]:
    seen: set[str] = set()
    values: list[AuditOutcome] = []
    for outcome in outcomes:
        if outcome.assessment is None or outcome.target.audit_url in seen:
            continue
        seen.add(outcome.target.audit_url)
        values.append(outcome)
    return values


def _build_archive(
    *,
    source_path: Path,
    outcomes: Sequence[AuditOutcome],
    generated_at: str,
) -> bytes:
    ranking = _ranking_rows(outcomes)
    failures = [row for row in ranking if row["audit_status"] == "failed"]
    successes = [outcome for outcome in outcomes if outcome.assessment is not None]
    unique_successes = _unique_successes(outcomes)
    unique_audit_urls = {outcome.target.audit_url for outcome in outcomes}
    manifest = {
        "schema_version": 1,
        "generated_at": generated_at,
        "source_discovery_zip": source_path.name,
        "source_discovery_sha256": _sha256_file(source_path),
        "business_targets": len(outcomes),
        "unique_audit_urls": len(unique_audit_urls),
        "audit_successes": len(successes),
        "audit_failures": len(failures),
        "unique_successful_site_audits": len(unique_successes),
        "persistence": "none",
        "technical_sort_weight": {
            "name": "attention_severity_weight_v1",
            "scope": "observable attention findings only; not commercial propensity",
            "severity_weights": _SEVERITY_WEIGHTS,
            "unavailable_findings_weighted": False,
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
            b"`technical_finding_weight` is only a deterministic ordering of observable "
            b"VERIDRA attention findings by severity. It does **not** estimate willingness "
            b"to buy, business size, budget, or expected conversion. `unavailable` findings "
            b"do not add weight. Duplicate normalized audit URLs are assessed once.\n",
        )
        for outcome in unique_successes:
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
    cache: dict[str, tuple[Assessment | None, str]] = {}
    unique_total = len({target.audit_url for target in targets})
    unique_index = 0
    for target in targets:
        cached = cache.get(target.audit_url)
        if cached is not None:
            assessment, error = cached
            outcomes.append(AuditOutcome(target=target, assessment=assessment, error=error))
            print(f"[Veridra] Reusing audit for {target.name}: {target.audit_url}")
            continue

        unique_index += 1
        print(
            f"[Veridra] Auditing site {unique_index}/{unique_total}: "
            f"{target.name} -> {target.audit_url}"
        )
        try:
            assessment = assessor(target.audit_url)
        except Exception as exc:
            error = str(exc)
            cache[target.audit_url] = (None, error)
            outcomes.append(AuditOutcome(target=target, assessment=None, error=error))
            print(f"[Veridra] Audit failed for {target.name}: {error}")
            continue
        cache[target.audit_url] = (assessment, "")
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
    unique_sites = len({item.target.audit_url for item in outcomes})
    print(
        json.dumps(
            {
                "input": str(input_path),
                "output": str(output_path),
                "business_targets": len(outcomes),
                "unique_sites": unique_sites,
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
