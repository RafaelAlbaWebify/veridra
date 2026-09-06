from __future__ import annotations

import argparse
import json
from pathlib import Path

from veridra.smb_validation_compare import compare


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-zip", type=Path, required=True)
    parser.add_argument(
        "--expectations",
        type=Path,
        default=Path("evidence/smb-validation/ie-dental-seed-expectations-v1.json"),
    )
    parser.add_argument(
        "--adjudications",
        type=Path,
        default=Path("evidence/smb-validation/ie-dental-seed-adjudications-v1.json"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    adjudications = args.adjudications if args.adjudications.exists() else None
    result = compare(args.audit_zip, args.expectations, adjudications)
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
