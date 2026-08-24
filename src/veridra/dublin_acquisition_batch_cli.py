from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .automated_discovery_evidence_cli import run as discovery_run
from .prospect_audit_evidence_cli import run as audit_run
from .prospect_qualification_evidence_cli import run as qualification_run
from .visual_outreach_evidence_strict_cli import run as visual_run

_DEFAULT_QUERIES = (
    "dentist in Dublin, IE",
    "dental clinic in Dublin, IE",
    "cosmetic dentist in Dublin, IE",
    "emergency dentist in Dublin, IE",
    "family dentist in Dublin, IE",
)
_TRACKING_KEYS = {
    "fbclid",
    "gad_source",
    "gclid",
    "gbraid",
    "wbraid",
    "y_source",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="veridra-dublin-acquisition-batch")
    parser.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--output-directory", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--max-new", type=int, default=35)
    parser.add_argument("--per-query-results", type=int, default=20)
    parser.add_argument("--max-scrolls", type=int, default=14)
    parser.add_argument("--max-seconds", type=float, default=75.0)
    parser.add_argument("--query", action="append", dest="queries")
    return parser


def _is_tracking_key(key: str) -> bool:
    folded = key.casefold()
    return folded.startswith("utm_") or folded in _TRACKING_KEYS


def _normalise_website(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return ""
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        return ""
    query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not _is_tracking_key(key)
    ]
    hostname = parsed.hostname.casefold()
    port = parsed.port
    scheme = parsed.scheme.casefold()
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        port = None
    netloc = hostname if port is None else f"{hostname}:{port}"
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, urlencode(query, doseq=True), ""))


def _load_observations(path: Path) -> list[dict[str, object]]:
    with zipfile.ZipFile(path) as archive:
        raw = json.loads(archive.read("captured_observations.json"))
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, dict)]


def _identity(row: dict[str, object]) -> tuple[str, str]:
    business = row.get("business")
    if not isinstance(business, dict):
        return "", ""
    provider_key = business.get("provider_key")
    key = provider_key.strip() if isinstance(provider_key, str) else ""
    return key, _normalise_website(business.get("website"))


def _historical_identities(downloads: Path) -> tuple[set[str], set[str], int]:
    provider_keys: set[str] = set()
    websites: set[str] = set()
    rows = 0
    for path in sorted(downloads.glob("VERIDRA_DISCOVERY_*.zip")):
        try:
            observations = _load_observations(path)
        except (OSError, KeyError, ValueError, zipfile.BadZipFile, json.JSONDecodeError):
            continue
        for row in observations:
            rows += 1
            key, website = _identity(row)
            if key:
                provider_keys.add(key)
            if website:
                websites.add(website)
    return provider_keys, websites, rows


def _latest(path: Path, pattern: str) -> Path:
    values = sorted(path.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)
    if not values:
        raise FileNotFoundError(f"Expected output matching {pattern} in {path}.")
    return values[0]


def _write_merged_discovery(
    path: Path,
    observations: list[dict[str, object]],
    *,
    queries: list[str],
    excluded_duplicates: int,
    historical_rows: int,
) -> None:
    generated_at = datetime.now(UTC).isoformat()
    reranked: list[dict[str, object]] = []
    for rank, row in enumerate(observations, start=1):
        clone = dict(row)
        clone["result_rank"] = rank
        reranked.append(clone)
    manifest = {
        "schema_version": 1,
        "generated_at": generated_at,
        "execution": "dublin-acquisition-batch",
        "query_variants": queries,
        "captured_count": len(reranked),
        "historical_rows_scanned": historical_rows,
        "excluded_duplicates": excluded_duplicates,
        "persistence": "none",
        "outreach": "none",
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        archive.writestr(
            "captured_observations.json",
            json.dumps(reranked, indent=2, ensure_ascii=False),
        )
        archive.writestr(
            "README.md",
            "# VERIDRA Dublin acquisition batch\n\n"
            "This discovery cohort contains only businesses not seen in prior local discovery ZIPs.\n"
            "No prospect state is persisted and no outreach is sent.\n",
        )


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_new < 1 or args.max_new > 100:
        raise ValueError("max-new must be between 1 and 100.")
    if args.per_query_results < 1 or args.per_query_results > 100:
        raise ValueError("per-query-results must be between 1 and 100.")

    queries = [item.strip() for item in (args.queries or _DEFAULT_QUERIES) if item.strip()]
    args.downloads.mkdir(parents=True, exist_ok=True)
    args.output_directory.mkdir(parents=True, exist_ok=True)
    historical_keys, historical_websites, historical_rows = _historical_identities(args.downloads)
    batch_keys: set[str] = set()
    batch_websites: set[str] = set()
    selected: list[dict[str, object]] = []
    excluded_duplicates = 0

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with tempfile.TemporaryDirectory(prefix="veridra-dublin-batch-") as temp_name:
        workdir = Path(temp_name)
        for query in queries:
            if len(selected) >= args.max_new:
                break
            print(f"[Veridra] Discovery variant: {query}")
            code = discovery_run(
                [
                    "--query",
                    query,
                    "--max-results",
                    str(args.per_query_results),
                    "--max-scrolls",
                    str(args.max_scrolls),
                    "--max-seconds",
                    str(args.max_seconds),
                    "--output-directory",
                    str(workdir),
                ]
            )
            if code == 2:
                return 2
            if code != 0:
                continue
            source = _latest(workdir, "VERIDRA_DISCOVERY_*.zip")
            for row in _load_observations(source):
                key, website = _identity(row)
                duplicate = bool(
                    (key and (key in historical_keys or key in batch_keys))
                    or (website and (website in historical_websites or website in batch_websites))
                )
                if duplicate:
                    excluded_duplicates += 1
                    continue
                if not key and not website:
                    continue
                selected.append(row)
                if key:
                    batch_keys.add(key)
                if website:
                    batch_websites.add(website)
                if len(selected) >= args.max_new:
                    break

        if not selected:
            print(
                json.dumps(
                    {
                        "new_businesses": 0,
                        "excluded_duplicates": excluded_duplicates,
                        "message": "No new Dublin dental businesses were found.",
                    },
                    indent=2,
                )
            )
            return 3

        discovery_zip = workdir / f"VERIDRA_DISCOVERY_DUBLIN_NEW_{stamp}.zip"
        _write_merged_discovery(
            discovery_zip,
            selected,
            queries=queries,
            excluded_duplicates=excluded_duplicates,
            historical_rows=historical_rows,
        )

        print(f"[Veridra] Auditing {len(selected)} new businesses...")
        if audit_run(["--input", str(discovery_zip), "--output-directory", str(workdir), "--max-targets", "100"]) != 0:
            return 4
        audit_zip = _latest(workdir, "VERIDRA_PROSPECT_AUDITS_*.zip")

        print("[Veridra] Collecting commercial qualification evidence...")
        if qualification_run(["--input", str(audit_zip), "--output-directory", str(workdir), "--max-targets", "100"]) != 0:
            return 5
        qualification_zip = _latest(workdir, "VERIDRA_QUALIFICATION_*.zip")

        print("[Veridra] Filtering for strict screenshot-ready evidence...")
        if visual_run(["--input", str(audit_zip), "--output-directory", str(workdir), "--max-businesses", "100"]) != 0:
            return 6
        visual_zip = _latest(workdir, "VERIDRA_VISUAL_EVIDENCE_STRICT_*.zip")

        output = args.output_directory / f"VERIDRA_DUBLIN_BATCH_{stamp}.zip"
        batch_manifest = {
            "schema_version": 1,
            "generated_at": datetime.now(UTC).isoformat(),
            "new_businesses": len(selected),
            "excluded_duplicates": excluded_duplicates,
            "historical_rows_scanned": historical_rows,
            "query_variants": queries,
            "persistence": "none",
            "outreach": "none",
            "stages": {
                "discovery": discovery_zip.name,
                "audit": audit_zip.name,
                "qualification": qualification_zip.name,
                "visual": visual_zip.name,
            },
        }
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "batch_manifest.json",
                json.dumps(batch_manifest, indent=2, ensure_ascii=False),
            )
            for stage_name, stage_path in (
                ("01-discovery.zip", discovery_zip),
                ("02-audits.zip", audit_zip),
                ("03-qualification.zip", qualification_zip),
                ("04-visual-evidence.zip", visual_zip),
            ):
                archive.write(stage_path, arcname=stage_name)

    print(
        json.dumps(
            {
                "output": str(output),
                "new_businesses": len(selected),
                "excluded_duplicates": excluded_duplicates,
                "historical_rows_scanned": historical_rows,
                "persistence": "none",
                "outreach": "none",
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
