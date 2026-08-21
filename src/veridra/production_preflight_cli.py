from __future__ import annotations

import argparse
import json

from .production_preflight import run_production_preflight


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate Veridra production configuration without starting the runtime."
    )
    parser.add_argument(
        "--require-stripe",
        action="store_true",
        help="Treat absent Stripe billing configuration as a critical failure.",
    )
    args = parser.parse_args()
    result = run_production_preflight(require_stripe=args.require_stripe)
    print(json.dumps(result.as_dict(), sort_keys=True, separators=(",", ":")))
    raise SystemExit(result.exit_code)


if __name__ == "__main__":
    main()
