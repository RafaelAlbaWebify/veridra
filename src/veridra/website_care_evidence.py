"""Local, CMS-neutral maintenance evidence ledger for the Webify operator.

No database migrations in VERIDRA, network calls or secret capture.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

CONTRACT = "webify_wordpress_care_cycle_v1"
MAX_BYTES = 256_000
SCHEMA = """
CREATE TABLE IF NOT EXISTS care_runs (
  evidence_sha256 TEXT PRIMARY KEY,
  website_ref TEXT NOT NULL,
  platform TEXT NOT NULL,
  contract TEXT NOT NULL,
  started_utc TEXT NOT NULL,
  finished_utc TEXT NOT NULL,
  inspected TEXT NOT NULL,
  backed_up TEXT NOT NULL,
  recovery_tested TEXT NOT NULL,
  passed INTEGER NOT NULL CHECK(passed IN (0,1)),
  ingested_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_care_runs_website
  ON care_runs(website_ref, finished_utc DESC);
"""


def normalize(data: object, *, website_ref: str, platform: str) -> dict[str, object]:
    if not isinstance(data, dict) or data.get("contract") != CONTRACT:
        raise ValueError("Unsupported evidence contract")
    if not isinstance(website_ref, str) or not website_ref.strip() or len(website_ref) > 128:
        raise ValueError("Invalid website reference")
    if platform not in {"wordpress", "static", "custom", "other_cms"}:
        raise ValueError("Unsupported platform")
    checks = data.get("steps")
    if not isinstance(checks, dict) or any(
        checks.get(k) not in {"PASS", "NOT_RUN", "FAIL"} 
        for k in ("inspect", "backup", "isolated_restore")
    ):
        raise ValueError("Incomplete or invalid checks")
    expected = all(checks[k] == "PASS" for k in ("inspect", "backup", "isolated_restore"))
    if type(data.get("passed")) is not bool or data["passed"] != expected:
        raise ValueError("Inconsistent overall result")
    started, finished = data.get("started_utc"), data.get("finished_utc")
    for value in (started, finished):
        if not isinstance(value, str):
            raise ValueError("Missing timestamps")
        try:
            if datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None:
                raise ValueError("Timestamp must include timezone")
        except ValueError as exc:
            raise ValueError("Invalid timestamp") from exc
    if datetime.fromisoformat(started.replace("Z", "+00:00")) > datetime.fromisoformat(
        finished.replace("Z", "+00:00")
    ):
        raise ValueError("Reversed timestamps")
    return {
        "website_ref": website_ref.strip(),
        "platform": platform,
        "contract": CONTRACT,
        "started_utc": started,
        "finished_utc": finished,
        "inspected": checks["inspect"],
        "backed_up": checks["backup"],
        "recovery_tested": checks["isolated_restore"],
        "passed": int(expected),
        "ingested_utc": datetime.now(timezone.utc).isoformat(),
    }


def import_evidence(path: Path, database: Path, website_ref: str, platform: str) -> bool:
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Evidence file too large")
    raw = path.read_bytes()
    data = json.loads(raw)
    record = normalize(data, website_ref=website_ref, platform=platform)
    checksum = hashlib.sha256(raw).hexdigest()
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as con:
        con.executescript(SCHEMA)
        cursor = con.execute(
            """INSERT OR IGNORE INTO care_runs
            (evidence_sha256, website_ref, platform, contract, started_utc, finished_utc,
             inspected, backed_up, recovery_tested, passed, ingested_utc)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                checksum, record["website_ref"], record["platform"], record["contract"],
                record["started_utc"], record["finished_utc"], record["inspected"],
                record["backed_up"], record["recovery_tested"], record["passed"],
                record["ingested_utc"],
            ),
        )
        return cursor.rowcount == 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Webify local Website Care evidence importer")
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--website-ref", required=True)
    parser.add_argument("--platform", choices=["wordpress", "static", "custom", "other_cms"], required=True)
    args = parser.parse_args()
    created = import_evidence(args.evidence, args.db, args.website_ref, args.platform)
    print(json.dumps({"ingested": created, "duplicate": not created, "website_ref": args.website_ref}))


if __name__ == "__main__":
    main()
