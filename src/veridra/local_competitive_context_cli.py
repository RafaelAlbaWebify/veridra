from __future__ import annotations

import argparse
import html
import json
import statistics
import zipfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="veridra-local-competitive-context")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--input-pattern", action="append", default=[])
    parser.add_argument("--visual-input", type=Path)
    parser.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--output-directory", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--label", default="local-businesses")
    return parser


def _latest(directory: Path, pattern: str) -> Path | None:
    values = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return values[0] if values else None


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _number(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _integer(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _website_key(value: object) -> str:
    text = _text(value)
    if not text:
        return ""
    parsed = urlsplit(text)
    return (parsed.hostname or "").casefold().removeprefix("www.")


def _safe_name(value: str) -> str:
    clean = "".join(char if char.isalnum() else "-" for char in value).strip("-")
    return "-".join(part for part in clean.split("-") if part)[:100] or "prospect"


def _row_identity(row: dict[str, object]) -> str:
    provider_key = _text(row.get("provider_key"))
    if provider_key:
        return f"provider:{provider_key}"
    website = _website_key(row.get("website"))
    if website:
        return f"website:{website}"
    return f"name:{_text(row.get('name')).casefold()}"


def _load_discovery(path: Path) -> list[dict[str, object]]:
    with zipfile.ZipFile(path) as archive:
        raw = json.loads(archive.read("captured_observations.json"))
    if not isinstance(raw, list):
        raise ValueError("captured_observations.json must contain a list.")
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        business = item.get("business")
        if not isinstance(business, dict):
            continue
        row = {"result_rank": item.get("result_rank"), **business}
        identity = _row_identity(row)
        if identity.endswith(":") or identity in seen:
            continue
        seen.add(identity)
        rows.append(row)
    return rows


def _merge_rows(sources: list[tuple[Path, list[dict[str, object]]]]) -> list[dict[str, object]]:
    merged: dict[str, dict[str, object]] = {}
    order: list[str] = []
    for source, rows in sources:
        for row in rows:
            identity = _row_identity(row)
            if identity not in merged:
                copy = dict(row)
                copy["source_discovery_files"] = [source.name]
                copy["cohort_member"] = True
                merged[identity] = copy
                order.append(identity)
                continue
            current = merged[identity]
            files = current.get("source_discovery_files")
            if isinstance(files, list) and source.name not in files:
                files.append(source.name)
            for key in (
                "website",
                "source_url",
                "category",
                "locality",
                "administrative_area",
                "rating",
                "review_count",
            ):
                if current.get(key) in (None, "") and row.get(key) not in (None, ""):
                    current[key] = row[key]
    return [merged[key] for key in order]


def _resolve_discovery_inputs(
    *,
    downloads: Path,
    direct_input: Path | None,
    patterns: list[str],
) -> list[Path]:
    if direct_input is not None:
        if not direct_input.is_file():
            raise FileNotFoundError(f"Discovery evidence ZIP was not found: {direct_input}")
        return [direct_input]
    if patterns:
        resolved: list[Path] = []
        for pattern in patterns:
            match = _latest(downloads, pattern)
            if match is not None and match not in resolved:
                resolved.append(match)
        if not resolved:
            raise FileNotFoundError("No discovery evidence ZIP matched the requested input patterns.")
        return resolved
    latest = _latest(downloads, "VERIDRA_DISCOVERY_*.zip")
    if latest is None:
        raise FileNotFoundError("No discovery evidence ZIP was found.")
    return [latest]


def _load_visual(
    path: Path | None,
) -> tuple[
    dict[str, list[dict[str, object]]],
    dict[str, list[dict[str, object]]],
    list[dict[str, object]],
]:
    by_name: dict[str, list[dict[str, object]]] = {}
    by_website: dict[str, list[dict[str, object]]] = {}
    anchors: list[dict[str, object]] = []
    if path is None or not path.is_file():
        return by_name, by_website, anchors
    with zipfile.ZipFile(path) as archive:
        raw = json.loads(archive.read("visual_evidence.json"))
    if not isinstance(raw, list):
        return by_name, by_website, anchors
    for row in raw:
        if not isinstance(row, dict):
            continue
        evidence = row.get("evidence")
        values = (
            [item for item in evidence if isinstance(item, dict)]
            if isinstance(evidence, list)
            else []
        )
        if not values:
            continue
        name = _text(row.get("business_name"))
        website_url = _text(row.get("audit_url"))
        website = _website_key(website_url)
        if name:
            by_name[name.casefold()] = values
        if website:
            by_website[website] = values
        if name or website:
            anchors.append(
                {
                    "name": name or website,
                    "website": website_url,
                    "source_url": "",
                    "category": "",
                    "rating": None,
                    "review_count": None,
                    "result_rank": None,
                    "source_discovery_files": [],
                    "cohort_member": False,
                }
            )
    return by_name, by_website, anchors


def _anchor_is_present(anchor: dict[str, object], rows: list[dict[str, object]]) -> bool:
    anchor_name = _text(anchor.get("name")).casefold()
    anchor_website = _website_key(anchor.get("website"))
    for row in rows:
        row_name = _text(row.get("name")).casefold()
        row_website = _website_key(row.get("website"))
        if anchor_website and row_website and anchor_website == row_website:
            return True
        if anchor_name and row_name and anchor_name == row_name:
            return True
    return False


def _append_missing_visual_anchors(
    rows: list[dict[str, object]], anchors: list[dict[str, object]]
) -> list[dict[str, object]]:
    result = [dict(row) for row in rows]
    for anchor in anchors:
        if not _anchor_is_present(anchor, result):
            result.append(dict(anchor))
    return result


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def build_benchmark(rows: list[dict[str, object]]) -> dict[str, object]:
    cohort_rows = [row for row in rows if row.get("cohort_member") is not False]
    ratings = [
        value for row in cohort_rows if (value := _number(row.get("rating"))) is not None
    ]
    reviews = [
        float(value)
        for row in cohort_rows
        if (value := _integer(row.get("review_count"))) is not None
    ]
    return {
        "business_count": len(cohort_rows),
        "rating_coverage": len(ratings),
        "rating_median": _median(ratings),
        "review_count_coverage": len(reviews),
        "review_count_median": _median(reviews),
        "website_field_coverage": sum(
            1 for row in cohort_rows if _website_key(row.get("website"))
        ),
        "website_field_note": (
            "A missing Google Maps website field is treated as collection coverage only and is not "
            "evidence that the business lacks a website."
        ),
        "photo_metric_status": "suppressed",
        "photo_metric_note": (
            "The first live Dublin run showed insufficient variance in the collected photo/profile "
            "signal, so it is retained only in raw discovery evidence and excluded from commercial "
            "comparison until a reliable photo count/freshness/coverage method is available."
        ),
    }


def _relative(
    value: float | None,
    median: float | None,
    *,
    stronger: float,
    weaker: float,
) -> str:
    if value is None or median is None:
        return "unknown"
    if median == 0:
        return "stronger" if value > 0 else "similar"
    ratio = value / median
    if ratio >= stronger:
        return "stronger"
    if ratio <= weaker:
        return "weaker"
    return "similar"


def _context_for(
    row: dict[str, object],
    benchmark: dict[str, object],
    visual_by_name: dict[str, list[dict[str, object]]],
    visual_by_website: dict[str, list[dict[str, object]]],
) -> dict[str, object]:
    name = _text(row.get("name"))
    website_url = _text(row.get("website"))
    website = _website_key(website_url)
    cohort_member = row.get("cohort_member") is not False
    rating = _number(row.get("rating")) if cohort_member else None
    reviews = _integer(row.get("review_count")) if cohort_member else None
    rating_median = _number(benchmark.get("rating_median"))
    review_median = _number(benchmark.get("review_count_median"))
    visual = visual_by_website.get(website) or visual_by_name.get(name.casefold()) or []

    strengths: list[str] = []
    gaps: list[str] = []
    opportunities: list[str] = []
    coverage_notes: list[str] = []

    if cohort_member:
        rating_position = _relative(rating, rating_median, stronger=1.03, weaker=0.96)
        if rating_position == "stronger":
            strengths.append("Customer rating is stronger than the local cohort median.")
        elif rating_position == "weaker":
            gaps.append("Customer rating is below the local cohort median.")

        review_position = _relative(
            float(reviews) if reviews is not None else None,
            review_median,
            stronger=1.5,
            weaker=0.5,
        )
        if review_position == "stronger":
            strengths.append("The business has substantially more review proof than the local median.")
        elif review_position == "weaker":
            gaps.append("The business has substantially less review proof than the local median.")

        if website:
            strengths.append("A website field was captured from the current local listing.")
        else:
            coverage_notes.append(
                "Google Maps did not provide a website field in this run; this does not mean the "
                "business has no website."
            )
    else:
        rating_position = "not_in_current_cohort"
        review_position = "not_in_current_cohort"
        coverage_notes.append(
            "This business was preserved from verified website evidence but was not returned in the "
            "current local-profile cohort, so rating/review comparisons are unavailable for this run."
        )
        if visual:
            strengths.append("Verified website evidence is available for this business.")

    for issue in visual[:2]:
        noticed = _text(issue.get("what_we_noticed"))
        if not noticed:
            continue
        gaps.append(f"Website evidence: {noticed}")
        issue_type = _text(issue.get("issue_type"))
        if issue_type == "mobile_overflow":
            opportunities.append(
                "Improve the mobile presentation so the website is easier to use than nearby alternatives."
            )
        elif issue_type == "broken_link":
            opportunities.append(
                "Remove the visible website dead end before using the site as a trust/conversion destination."
            )

    if cohort_member and review_position == "stronger" and visual:
        opportunities.insert(
            0,
            "The business already has strong customer proof; make the website presentation match that reputation.",
        )

    unique_opportunities: list[str] = []
    for item in opportunities:
        if item not in unique_opportunities:
            unique_opportunities.append(item)

    source_files = row.get("source_discovery_files")
    return {
        "result_rank": row.get("result_rank"),
        "business_name": name,
        "website": website_url,
        "source_url": _text(row.get("source_url")),
        "category": _text(row.get("category")),
        "cohort_member": cohort_member,
        "source_discovery_files": source_files if isinstance(source_files, list) else [],
        "signals": {
            "rating": rating,
            "review_count": reviews,
            "rating_vs_local_median": rating_position,
            "review_volume_vs_local_median": review_position,
            "photo_metric": "suppressed",
        },
        "strengths": strengths,
        "competitive_gaps": gaps,
        "data_coverage_notes": coverage_notes,
        "webify_opportunities": unique_opportunities[:3],
        "website_visual_evidence_count": len(visual),
    }


def _summary_html(benchmark: dict[str, object], contexts: list[dict[str, object]]) -> str:
    anchor_count = sum(1 for context in contexts if context.get("cohort_member") is False)
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'><title>VERIDRA local competitive context</title>",
        "<style>body{font-family:Arial,sans-serif;max-width:1100px;margin:40px auto;padding:0 20px;color:#202124}section{border-top:1px solid #ddd;padding:22px 0}table{border-collapse:collapse}td,th{padding:7px 12px;border:1px solid #ddd;text-align:left}li{margin:7px 0}.muted{color:#68707a}</style></head><body>",
        "<h1>Local Competitive Context</h1>",
        f"<p>Businesses in current local cohort: <strong>{benchmark['business_count']}</strong>. Verified evidence anchors outside the current cohort: <strong>{anchor_count}</strong>. This is relative commercial context, not a global score.</p>",
        "<table><tr><th>Signal</th><th>Local median</th><th>Coverage</th></tr>",
        f"<tr><td>Google rating</td><td>{html.escape(str(benchmark.get('rating_median') or '—'))}</td><td>{benchmark['rating_coverage']}</td></tr>",
        f"<tr><td>Review count</td><td>{html.escape(str(benchmark.get('review_count_median') or '—'))}</td><td>{benchmark['review_count_coverage']}</td></tr></table>",
        "<p class='muted'>Missing Maps website fields are collection gaps only, not evidence that a business lacks a website. The photo/profile metric remains suppressed. Review quality here means measurable reputation strength (rating and review volume); review text sentiment is not inferred.</p>",
        "<p class='muted'>Rating/review comparisons are factual local context. Webify opportunities are generated only from collected evidence of an action Webify can plausibly improve.</p>",
    ]
    for context in contexts:
        parts.append(f"<section><h2>{html.escape(_text(context.get('business_name')))}</h2>")
        if context.get("cohort_member") is False:
            parts.append(
                "<p class='muted'><strong>Verified evidence anchor:</strong> not returned in the current local-profile cohort.</p>"
            )
        signals = context.get("signals") if isinstance(context.get("signals"), dict) else {}
        parts.append(
            f"<p>Rating: <strong>{html.escape(str(signals.get('rating') or '—'))}</strong> · Reviews: <strong>{html.escape(str(signals.get('review_count') or '—'))}</strong> · Website visual findings: <strong>{context.get('website_visual_evidence_count', 0)}</strong></p>"
        )
        for title, key in (
            ("Strengths", "strengths"),
            ("Competitive gaps", "competitive_gaps"),
            ("Data coverage notes", "data_coverage_notes"),
            ("Webify opportunities", "webify_opportunities"),
        ):
            values = context.get(key)
            parts.append(f"<h3>{title}</h3><ul>")
            if isinstance(values, list) and values:
                parts.extend(f"<li>{html.escape(_text(value))}</li>" for value in values)
            else:
                parts.append("<li>No strong evidence-backed signal from the available evidence.</li>")
            parts.append("</ul>")
        parts.append("</section>")
    parts.append("</body></html>")
    return "".join(parts)


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    discovery_files = _resolve_discovery_inputs(
        downloads=args.downloads,
        direct_input=args.input,
        patterns=list(args.input_pattern),
    )
    visual = args.visual_input or _latest(args.downloads, "VERIDRA_VISUAL_EVIDENCE_STRICT_*.zip")
    sources = [(path, _load_discovery(path)) for path in discovery_files]
    cohort_rows = _merge_rows(sources)
    if not cohort_rows:
        raise ValueError("Discovery evidence contains no businesses.")
    visual_by_name, visual_by_website, visual_anchors = _load_visual(visual)
    benchmark = build_benchmark(cohort_rows)
    rows = _append_missing_visual_anchors(cohort_rows, visual_anchors)
    contexts = [
        _context_for(row, benchmark, visual_by_name, visual_by_website)
        for row in rows
    ]
    anchor_count = sum(1 for context in contexts if context.get("cohort_member") is False)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    label = _safe_name(args.label).upper()
    output = args.output_directory / f"VERIDRA_COMPETITIVE_{label}_{stamp}.zip"
    args.output_directory.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 3,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_discovery_files": [path.name for path in discovery_files],
        "source_visual_evidence": visual.name if visual is not None else None,
        "businesses_compared": len(contexts),
        "local_cohort_businesses": len(cohort_rows),
        "verified_evidence_anchors_outside_cohort": anchor_count,
        "comparison_method": "deduped multi-query local cohort medians; no global score",
        "review_quality_method": "rating + review volume only; review text is not collected",
        "photo_metric_status": "suppressed after insufficient variance in first live run",
        "website_absence_rule": "missing Maps website field is coverage only, not evidence of no website",
        "anchor_rule": "verified visual-evidence businesses are retained even when absent from the current Maps cohort",
        "opportunity_rule": "Webify opportunities require evidence of a Webify-fixable action",
        "persistence": "none",
        "outreach": "none",
    }
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        archive.writestr("local_benchmark.json", json.dumps(benchmark, indent=2, ensure_ascii=False))
        archive.writestr("competitive_context.json", json.dumps(contexts, indent=2, ensure_ascii=False))
        archive.writestr("summary.html", _summary_html(benchmark, contexts))
        archive.writestr(
            "README.md",
            "# VERIDRA Local Competitive Context\n\nRead-only relative comparison for a deduped multi-query local cohort, plus verified website-evidence anchors that may be absent from the current Maps results. It does not send outreach, persist prospect state, or produce a universal score. Rating and review volume are factual context only. A missing Maps website field is a collection gap, not proof that no website exists. Photo-based commercial claims and review-text sentiment remain excluded until reliable evidence is collected. Webify opportunities are generated only from evidence of an action Webify can plausibly improve.\n",
        )
        for context in contexts:
            folder = f"prospects/{_safe_name(_text(context.get('business_name')))}"
            archive.writestr(
                f"{folder}/competitive_context.json",
                json.dumps(context, indent=2, ensure_ascii=False),
            )
    print(
        json.dumps(
            {
                "inputs": [str(path) for path in discovery_files],
                "visual_input": str(visual) if visual is not None else None,
                "output": str(output),
                "businesses_compared": len(contexts),
                "local_cohort_businesses": len(cohort_rows),
                "verified_evidence_anchors_outside_cohort": anchor_count,
                "rating_coverage": benchmark["rating_coverage"],
                "review_count_coverage": benchmark["review_count_coverage"],
                "photo_metric_status": "suppressed",
                "persistence": "none",
                "outreach": "none",
            },
            indent=2,
        )
    )
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
