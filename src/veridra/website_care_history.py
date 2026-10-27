"""Read-only query of bounded Website Care evidence (local, not customer API)."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

LIMIT_MAX = 200


def read_history(
    database: Path, *, website_ref: str | None = None, limit: int = 25
) -> list[dict[str, object]]:
    if not 1 <= limit <= LIMIT_MAX:
        raise ValueError("Limit out of range")
    if website_ref is not None and (not website_ref.strip() or len(website_ref) > 128):
        raise ValueError("Invalid website reference")
    if not database.is_file():
        return []
    with sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True) as con:
        con.row_factory = sqlite3.Row
        if website_ref is None:
            rows = con.execute(
                """SELECT website_ref, platform, started_utc, finished_utc,
                inspected, backed_up, recovery_tested, passed
                FROM care_runs ORDER BY finished_utc DESC LIMIT ?""",
                (limit,),
            )
        else:
            rows = con.execute(
                """SELECT website_ref, platform, started_utc, finished_utc,
                inspected, backed_up, recovery_tested, passed
                FROM care_runs WHERE website_ref = ?
                ORDER BY finished_utc DESC LIMIT ?""",
                (website_ref, limit),
            )
        return [dict(row) for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description="View Webify Website Care history")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--website-ref")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()
    print(
        json.dumps(
            {"runs": read_history(args.db, website_ref=args.website_ref, limit=args.limit)},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
