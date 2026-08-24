from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from .automated_discovery_evidence_cli import run as discovery_run
from .dublin_acquisition_batch_cli import (
    _DEFAULT_QUERIES,
    _historical_identities,
    _identity,
    _latest,
    _load_observations,
    _write_merged_discovery,
)
from .prospect_audit_evidence_cli import run as audit_run
from .prospect_qualification_evidence_cli import run as qualification_run
from .visual_outreach_evidence_strict_cli import run as visual_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="veridra-dublin-acquisition-batch")
    parser.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--output-directory", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--max-new", type=int, default=35)
    parser.add_argument("--per-query-results", type=int, default=20)
    parser.add_argument("--max-scrolls", type=int, default=14)
    parser.add_argument("--max-seconds", type=float, default=75.0)
    parser.add_argument("--query", action="append", dest="queries")
    parser.add_argument("--discovery-retries", type=int, default=2)
    parser.add_argument("--startup-wait-seconds", type=float, default=8.0)
    return parser


def _run_discovery_variant(
    *,
    query: str,
    workdir: Path,
    per_query_results: int,
    max_scrolls: int,
    max_seconds: float,
    retries: int,
    startup_wait_seconds: float,
) -> bool:
    for attempt in range(retries + 1):
        wait_seconds = startup_wait_seconds + (attempt * 4.0)
        if attempt:
            print(
                f"[Veridra] Retrying discovery variant {attempt}/{retries} "
                f"after Maps did not expose a results panel..."
            )
        code = discovery_run(
            [
                "--query",
                query,
                "--max-results",
                str(per_query_results),
                "--max-scrolls",
                str(max_scrolls),
                "--max-seconds",
                str(max_seconds),
                "--startup-wait-seconds",
                str(wait_seconds),
                "--output-directory",
                str(workdir),
            ]
        )
        if code == 0:
            return True
        if code != 2:
            return False
    print(f"[Veridra] Skipping discovery variant after retries: {query}")
    return False


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_new < 1 or args.max_new > 100:
        raise ValueError("max-new must be between 1 and 100.")
    if args.per_query_results < 1 or args.per_query_results > 100:
        raise ValueError("per-query-results must be between 1 and 100.")
    if args.discovery_retries < 0 or args.discovery_retries > 5:
        raise ValueError("discovery-retries must be between 0 and 5.")
    if args.startup_wait_seconds < 0 or args.startup_wait_seconds > 60:
        raise ValueError("startup-wait-seconds must be between 0 and 60.")

    queries = [item.strip() for item in (args.queries or _DEFAULT_QUERIES) if item.strip()]
    args.downloads.mkdir(parents=True, exist_ok=True)
    args.output_directory.mkdir(parents=True, exist_ok=True)
    historical_keys, historical_websites, historical_rows = _historical_identities(args.downloads)
    batch_keys: set[str] = set()
    batch_websites: set[str] = set()
    selected: list[dict[str, object]] = []
    excluded_duplicates = 0
    failed_variants: list[str] = []

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with tempfile.TemporaryDirectory(prefix="veridra-dublin-batch-") as temp_name:
        workdir = Path(temp_name)
        for query in queries:
            if len(selected) >= args.max_new:
                break
            print(f"[Veridra] Discovery variant: {query}")
            success = _run_discovery_variant(
                query=query,
                workdir=workdir,
                per_query_results=args.per_query_results,
                max_scrolls=args.max_scrolls,
                max_seconds=args.max_seconds,
                retries=args.discovery_retries,
                startup_wait_seconds=args.startup_wait_seconds,
            )
            if not success:
                failed_variants.append(query)
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
                        "failed_query_variants": failed_variants,
                        "message": "No new Dublin dental businesses were found.",
                    },
                    indent=2,
                    ensure_ascii=False,
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
        if audit_run(
            ["--input", str(discovery_zip), "--output-directory", str(workdir), "--max-targets", "100"]
        ) != 0:
            return 4
        audit_zip = _latest(workdir, "VERIDRA_PROSPECT_AUDITS_*.zip")

        print("[Veridra] Collecting commercial qualification evidence...")
        if qualification_run(
            ["--input", str(audit_zip), "--output-directory", str(workdir), "--max-targets", "100"]
        ) != 0:
            return 5
        qualification_zip = _latest(workdir, "VERIDRA_QUALIFICATION_*.zip")

        print("[Veridra] Filtering for strict screenshot-ready evidence...")
        if visual_run(
            ["--input", str(audit_zip), "--output-directory", str(workdir), "--max-businesses", "100"]
        ) != 0:
            return 6
        visual_zip = _latest(workdir, "VERIDRA_VISUAL_EVIDENCE_STRICT_*.zip")

        output = args.output_directory / f"VERIDRA_DUBLIN_BATCH_{stamp}.zip"
        batch_manifest = {
            "schema_version": 2,
            "generated_at": datetime.now(UTC).isoformat(),
            "new_businesses": len(selected),
            "excluded_duplicates": excluded_duplicates,
            "historical_rows_scanned": historical_rows,
            "query_variants": queries,
            "failed_query_variants": failed_variants,
            "discovery_retries": args.discovery_retries,
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
                "failed_query_variants": failed_variants,
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
