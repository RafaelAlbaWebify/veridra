"""Offline/local city-study workbench. Never launches a browser or contacts prospects."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .market_intelligence import (
    DEFAULT_SECTORS,
    add_observations,
    dashboard,
    import_review,
    load,
    plan,
    save,
    snapshot,
    snapshot_hash,
)
from .prospect_discovery import ObservedBusiness


def main() -> None:
    p = argparse.ArgumentParser(description="VERIDRA City Market Intelligence")
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("new")
    a.add_argument("study", type=Path)
    a.add_argument("--city", required=True)
    a.add_argument("--country", required=True)
    a.add_argument("--sectors", default=",".join(DEFAULT_SECTORS))
    a = sub.add_parser("ingest")
    a.add_argument("study", type=Path)
    a.add_argument("--sector", required=True)
    a.add_argument("--observations", type=Path, required=True)
    for name in ("export", "import-review", "dashboard"):
        a = sub.add_parser(name)
        a.add_argument("study", type=Path)
        a.add_argument("--output", type=Path)
        if name == "import-review":
            a.add_argument("--review", type=Path, required=True)
    args = p.parse_args()
    if args.command == "new":
        save(plan(args.city, args.country, tuple(args.sectors.split(","))), args.study)
        print(f"Study created: {args.study}")
        return
    study = load(args.study)
    if args.command == "ingest":
        raw = json.loads(args.observations.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise SystemExit("Observations must be a JSON list")
        records = [ObservedBusiness.model_validate(x) for x in raw]
        save(add_observations(study, args.sector, records), args.study)
        print(f"Imported {len(records)} observations")
    elif args.command == "export":
        output = args.output or args.study.with_name("VERIDRA_MARKET_ANALYSIS_INPUT.json")
        data = snapshot(study)
        data["snapshot_sha256"] = snapshot_hash(study)
        output.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(output)
    elif args.command == "import-review":
        review = json.loads(args.review.read_text(encoding="utf-8"))
        save(import_review(study, review), args.study)
        print("AI market review imported")
    elif args.command == "dashboard":
        output = args.output or args.study.with_suffix(".html")
        output.write_text(dashboard(study), encoding="utf-8")
        print(output)


if __name__ == "__main__":
    main()
