from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from collections.abc import Sequence
from pathlib import Path

from .visual_outreach_hardened_cli import run as visual_run

_AUDIT_MEMBER = "02-audits.zip"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="veridra-dublin-visual-reprocess")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--output-directory", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--max-businesses", type=int, default=100)
    parser.add_argument("--navigation-timeout-ms", type=int, default=20_000)
    return parser


def latest_dublin_batch(downloads: Path) -> Path:
    values = sorted(
        downloads.glob("VERIDRA_DUBLIN_BATCH_*.zip"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if not values:
        raise FileNotFoundError(f"No VERIDRA_DUBLIN_BATCH_*.zip was found in {downloads}.")
    return values[0]


def extract_audit_zip(batch_path: Path, output_path: Path) -> None:
    with zipfile.ZipFile(batch_path) as archive:
        try:
            payload = archive.read(_AUDIT_MEMBER)
        except KeyError as exc:
            raise ValueError(f"Dublin batch does not contain {_AUDIT_MEMBER}.") from exc
    output_path.write_bytes(payload)


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    batch = args.input or latest_dublin_batch(args.downloads)
    if not batch.is_file():
        raise FileNotFoundError(f"Dublin batch was not found: {batch}")
    args.output_directory.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="veridra-dublin-visual-reprocess-") as temp_name:
        audit_path = Path(temp_name) / "VERIDRA_PROSPECT_AUDITS_REPROCESS.zip"
        extract_audit_zip(batch, audit_path)
        code = visual_run(
            [
                "--input",
                str(audit_path),
                "--output-directory",
                str(args.output_directory),
                "--max-businesses",
                str(args.max_businesses),
                "--navigation-timeout-ms",
                str(args.navigation_timeout_ms),
                "--country-code",
                "IE",
            ]
        )
        if code != 0:
            return code

    outputs = sorted(
        args.output_directory.glob("VERIDRA_VISUAL_EVIDENCE_STRICT_*.zip"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if not outputs:
        raise FileNotFoundError("Regenerated visual evidence ZIP was not created.")
    print(
        json.dumps(
            {
                "source_batch": str(batch),
                "output": str(outputs[0]),
                "country_code": "IE",
                "rediscovery": "none",
                "persistence": "none",
                "outreach": "none",
            },
            indent=2,
        )
    )
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
