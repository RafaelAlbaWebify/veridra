from __future__ import annotations

import argparse
import json

from .deployment_acceptance import run_deployment_acceptance


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate a deployed Veridra HTTPS origin after infrastructure provisioning."
    )
    parser.add_argument(
        "--origin",
        required=True,
        help="Bare public HTTPS origin, for example https://app.example.com",
    )
    args = parser.parse_args()
    result = run_deployment_acceptance(args.origin)
    print(json.dumps(result.as_dict(), sort_keys=True, separators=(",", ":")))
    raise SystemExit(result.exit_code)


if __name__ == "__main__":
    main()
