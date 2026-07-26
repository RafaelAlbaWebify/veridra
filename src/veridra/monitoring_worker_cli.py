from __future__ import annotations

import argparse
import os
from pathlib import Path

from .monitoring_worker import MonitoringWorker


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lease and execute a bounded number of durable tenant monitoring jobs."
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--tenant-data-root",
        type=Path,
        default=None,
        help="Tenant data root. Defaults to VERIDRA_TENANT_DATA_ROOT.",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    configured = args.tenant_data_root or os.environ.get("VERIDRA_TENANT_DATA_ROOT")
    if configured is None:
        raise SystemExit(
            "Tenant data root is required via --tenant-data-root or VERIDRA_TENANT_DATA_ROOT."
        )
    root = Path(configured).expanduser().resolve()
    result = MonitoringWorker(root=root).run_once(limit=args.limit)
    print(
        f"leased={result.leased} succeeded={result.succeeded} "
        f"retried={result.retried} failed={result.failed}"
    )


if __name__ == "__main__":
    main()
