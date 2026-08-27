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
from .website_verification import (
    WebsiteVerificationStatus,
    load_website_verifications,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="veridra-market-opportunity")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--website-verifications", type=Path)
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
        "website_verification_required",
        "website_verification_status",
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

    verification_path = args.website_verifications or _latest(
        args.downloads, "VERIDRA_WEBSITE_VERIFICATIONS_*.json"
    )
    verifications = (
        load_website_verifications(verification_path)
        if verification_path is not None and verification_path.is_file()
        else {}
    )

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
    applied_verifications = 0
    for row in evidence:
        business_name = _text(row.get("business_name"))
        website_url = _text(row.get("website_url")) or None
        verification = verifications.get(business_name.casefold())
        website_absence_verified = False
        verification_status = ""
        verification_evidence_urls: tuple[str, ...] = ()
        verification_note = ""
        if verification is not None:
            applied_verifications += 1
            verification_status = verification.status.value
            verification_evidence_urls = verification.evidence_urls
            verification_note = verification.note or ""
            if verification.status is WebsiteVerificationStatus.website_found:
                website_url = verification.website_url
            elif verification.status is WebsiteVerificationStatus.absence_verified:
                website_url = None
                website_absence_verified = True

        assessment = assess_market_opportunity(
            website_url=website_url,
            website_absence_verified=website_absence_verified,
            booking_links=_strings(row.get("booking_links")),
            rating=_number(row.get("rating")),
            review_count=_integer(row.get("review_count")),
            benchmarks=benchmarks,
        )
        ranked.append(
            {
                "business_name": business_name,
                "score": assessment.score,
                "band": assessment.band.value,
                "digital_gap_score": assessment.digital_gap_score,
                "activity_score": assessment.activity_score,
                "website_verification_required": assessment.website_verification_required,
                "website_verification_status": verification_status,
                "website_verification_evidence_urls": list(verification_evidence_urls),
                "website_verification_note": verification_note,
                "rating": _number(row.get("rating")),
                "review_count": _integer(row.get("review_count")),
                "website_url": website_url or "",
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
    verification_required = sum(
        1 for row in ranked if row.get("website_verification_required") is True
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    args.output_directory.mkdir(parents=True, exist_ok=True)
    output = args.output_directory / f"VERIDRA_MARKET_OPPORTUNITIES_{stamp}.zip"
    manifest = {
        "schema_version": 3,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_gbp_market_evidence": input_path.name,
        "source_website_verifications": verification_path.name if verification_path else None,
        "website_verifications_applied": applied_verifications,
        "businesses_ranked": len(ranked),
        "priority": priority,
        "high": high,
        "medium": medium,
        "low": low,
        "website_verification_required": verification_required,
        "review_benchmarks": {
            "q1": benchmarks.review_q1,
            "median": benchmarks.review_median,
            "q3": benchmarks.review_q3,
        },
        "scoring_rule": (
            "Maps/GBP website absence is treated as unverified. Independent website verification "
            "may either supply a website URL or explicitly verify absence before the full no-site "
            "boost can apply. Review volume is market-relative activity evidence."
        ),
        "reputation_rule": (
            "An established rating below 4.2 blocks Priority because the business may have a "
            "non-digital reputation problem that Webify cannot solve by itself."
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
            "Post-enrichment market triage with optional independent website verification. "
            "Maps/GBP absence alone remains unverified. A verification file may supply a found "
            "website, verify absence, or record an inconclusive check. No prospect state is "
            "mutated and no outreach is sent.\n",
        )

    top = [
        {
            "rank": row["rank"],
            "business": row["business_name"],
            "score": row["score"],
            "band": row["band"],
            "reviews": row["review_count"],
            "website": bool(row["website_url"]),
            "website_verification_required": row["website_verification_required"],
            "website_verification_status": row["website_verification_status"],
            "booking_links": row["booking_link_count"],
        }
        for row in ranked[:20]
    ]
    print(
        json.dumps(
            {
                "input": str(input_path),
                "website_verifications": str(verification_path) if verification_path else None,
                "website_verifications_applied": applied_verifications,
                "output": str(output),
                "businesses_ranked": len(ranked),
                "bands": {
                    "priority": priority,
                    "high": high,
                    "medium": medium,
                    "low": low,
                },
                "website_verification_required": verification_required,
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
