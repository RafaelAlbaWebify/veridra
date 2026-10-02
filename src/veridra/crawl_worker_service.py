from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from .crawl_worker import CrawlWorker


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Continuously execute durable tenant crawl jobs with bounded polling."
    )
    parser.add_argument("--tenant-data-root", type=Path, default=None)
    parser.add_argument("--interval", type=int, default=10)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--once", action="store_true")
    return parser


def main() -> None:
    args = _parser().parse_args()
    configured = args.tenant_data_root or os.environ.get("VERIDRA_TENANT_DATA_ROOT")
    if configured is None:
        raise SystemExit(
            "Tenant data root is required via --tenant-data-root or VERIDRA_TENANT_DATA_ROOT."
        )
    if args.interval < 2 or args.interval > 3600:
        raise SystemExit("--interval must be between 2 and 3600 seconds.")
    if args.limit < 1 or args.limit > 100:
        raise SystemExit("--limit must be between 1 and 100.")

    root = Path(configured).expanduser().resolve()
    while True:
        result = CrawlWorker(root=root).run_once(limit=args.limit)
        print(
            f"leased={result.leased} succeeded={result.succeeded} "
            f"retried={result.retried} failed={result.failed}",
            flush=True,
        )
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
