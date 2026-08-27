from __future__ import annotations

import argparse
import csv
import io
import json
import zipfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from .market_opportunity import assess_market_opportunity, review_benchmarks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="veridra-market-opportunity")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--output-directory", type=Path, default=Path.home() / "Downloads")
    return parser


def _latest(directory: Path, pattern: str) -> Path | None:
    matches = sorted(directory.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _integer(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _number(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item.strip())


def _load(path: Path) -> list[dict[str, object]]:
    with zipfile.ZipFile(path) as archive:
        raw = json.loads(archive.read("gbp_market_evidence.json"))
    if not isinstance(raw, list):
        raise ValueError("gbp_market_evidence.json must contain a list.")
    return [item for item in raw if isinstance(item, dict)]


def _csv_bytes(rows: list[dict[str, object]]) -> bytes:
    buffer = io.StringIO(newline="")
    fields = (
        "rank",
        "business_name",
        "score",
        "band",
        "digital_gap_score",
        "activity_score",
        "rating",
        "review_count",
        "website_url",
        "booking_link_count",
        "first_query_text",
        "first_result_rank",
        "observation_count",
        "reasons",
    )
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in fields})
    return buffer.getvalue().encode("utf-8")


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    input_path = args.input or _latest(args.downloads, "VERIDRA_GBP_MARKET_EVIDENCE_*.zip")
    if input_path is None or not input_path.is_file():
        raise FileNotFoundError("No VERIDRA GBP market-evidence ZIP was found.")

    evidence = [row for row in _load(input_path) if row.get("collection_status") == "ok"]
    if not evidence:
        raise ValueError("The GBP market-evidence ZIP contains no successful observations.")

    counts = [
        count
        for row in evidence
        if (count := _integer(row.get("review_count"))) is not None
    ]
    benchmarks = review_benchmarks(counts)

    ranked: list[dict[str, object]] = []
    for row in evidence:
        assessment = assess_market_opportunity(
            website_url=_text(row.get("website_url")) or None,
            booking_links=_strings(row.get("booking_links")),
            rating=_number(row.get("rating")),
            review_count=_integer(row.get("review_count")),
            benchmarks=benchmarks,
        )
        ranked.append(
            {
                "business_name": _text(row.get("business_name")),
                "score": assessment.score,
                "band": assessment.band.value,
                "digital_gap_score": assessment.digital_gap_score,
                "activity_score": assessment.activity_score,
                "rating": _number(row.get("rating")),
                "review_count": _integer(row.get("review_count")),
                "website_url": _text(row.get("website_url")),
                "booking_link_count": len(_strings(row.get("booking_links"))),
                "first_query_text": _text(row.get("first_query_text")),
                "first_result_rank": row.get("first_result_rank"),
                "seen_in_queries": row.get("seen_in_queries"),
                "observation_count": row.get("observation_count"),
                "provider_key": row.get("provider_key"),
                "source_url": row.get("source_url"),
                "reasons": list(assessment.reasons),
            }
        )

    ranked.sort(
        key=lambda row: (
            -(_integer(row.get("score")) or 0),
            -(_integer(row.get("review_count")) or 0),
            _text(row.get("business_name")).casefold(),
        )
    )
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index
        row["reasons_text"] = " | ".join(_strings(row.get("reasons")))
        row["reasons"] = row["reasons_text"]

    priority = sum(1 for row in ranked if row.get("band") == "priority")
    high = sum(1 for row in ranked if row.get("band") == "high")
    medium = sum(1 for row in ranked if row.get("band") == "medium")
    low = sum(1 for row in ranked if row.get("band") == "low")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    args.output_directory.mkdir(parents=True, exist_ok=True)
    output = args.output_directory / f"VERIDRA_MARKET_OPPORTUNITIES_{stamp}.zip"
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_gbp_market_evidence": input_path.name,
        "businesses_ranked": len(ranked),
        "priority": priority,
        "high": high,
        "medium": medium,
        "low": low,
        "review_benchmarks": {
            "q1": benchmarks.review_q1,
            "median": benchmarks.review_median,
            "q3": benchmarks.review_q3,
        },
        "scoring_rule": (
            "Ranking occurs only after full-market GBP enrichment. Confirmed website absence and "
            "observed booking-action absence are digital-gap signals; review volume is used only "
            "as market-relative customer-activity evidence. Rating does not add negative-gap "
            "points."
        ),
        "photo_rule": "Raw Google Maps photo-control counts are not scored.",
        "persistence": "none",
        "outreach": "none",
    }

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        archive.writestr(
            "ranked_opportunities.json",
            json.dumps(ranked, indent=2, ensure_ascii=False),
        )
        archive.writestr("ranked_opportunities.csv", _csv_bytes(ranked))
        archive.writestr(
            "README.md",
            "# VERIDRA Market Opportunities\n\n"
            "Post-enrichment market triage. The ranking is applied only after the deduplicated "
            "market has been enriched with public GBP evidence. Missing website is treated as a "
            "strong digital gap only after the GBP detail-page pass. Review volume is "
            "market-relative activity evidence, not a weakness score. Raw photo controls are not "
            "scored. No prospect state is mutated and no outreach is sent.\n",
        )

    top = [
        {
            "rank": row["rank"],
            "business": row["business_name"],
            "score": row["score"],
            "band": row["band"],
            "reviews": row["review_count"],
            "website": bool(row["website_url"]),
            "booking_links": row["booking_link_count"],
        }
        for row in ranked[:20]
    ]
    print(
        json.dumps(
            {
                "input": str(input_path),
                "output": str(output),
                "businesses_ranked": len(ranked),
                "bands": {
                    "priority": priority,
                    "high": high,
                    "medium": medium,
                    "low": low,
                },
                "review_benchmarks": manifest["review_benchmarks"],
                "top_20": top,
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
