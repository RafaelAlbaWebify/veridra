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
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    return host


def _safe_name(value: str) -> str:
    clean = "".join(char if char.isalnum() else "-" for char in value).strip("-")
    return "-".join(part for part in clean.split("-") if part)[:100] or "prospect"


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
        provider_key = _text(business.get("provider_key"))
        website = _website_key(business.get("website"))
        identity = provider_key or website or _text(business.get("name")).casefold()
        if not identity or identity in seen:
            continue
        seen.add(identity)
        rows.append({"result_rank": item.get("result_rank"), **business})
    return rows


def _load_visual(path: Path | None) -> tuple[dict[str, list[dict[str, object]]], dict[str, list[dict[str, object]]]]:
    by_name: dict[str, list[dict[str, object]]] = {}
    by_website: dict[str, list[dict[str, object]]] = {}
    if path is None or not path.is_file():
        return by_name, by_website
    with zipfile.ZipFile(path) as archive:
        raw = json.loads(archive.read("visual_evidence.json"))
    if not isinstance(raw, list):
        return by_name, by_website
    for row in raw:
        if not isinstance(row, dict):
            continue
        evidence = row.get("evidence")
        values = [item for item in evidence if isinstance(item, dict)] if isinstance(evidence, list) else []
        if not values:
            continue
        name = _text(row.get("business_name")).casefold()
        website = _website_key(row.get("audit_url"))
        if name:
            by_name[name] = values
        if website:
            by_website[website] = values
    return by_name, by_website


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def build_benchmark(rows: list[dict[str, object]]) -> dict[str, object]:
    ratings = [value for row in rows if (value := _number(row.get("rating"))) is not None]
    reviews = [float(value) for row in rows if (value := _integer(row.get("review_count"))) is not None]
    photos = [
        float(value)
        for row in rows
        if (value := _integer(row.get("profile_photo_signal_count"))) is not None
    ]
    return {
        "business_count": len(rows),
        "rating_coverage": len(ratings),
        "rating_median": _median(ratings),
        "review_count_coverage": len(reviews),
        "review_count_median": _median(reviews),
        "profile_photo_signal_coverage": len(photos),
        "profile_photo_signal_median": _median(photos),
        "website_coverage": sum(1 for row in rows if _website_key(row.get("website"))),
        "photo_metric_note": (
            "Profile photo signal is a relative count of visible Google Maps photo-labelled controls, "
            "not a claimed total number of business photos."
        ),
    }


def _relative(value: float | None, median: float | None, *, stronger: float, weaker: float) -> str:
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
    website = _website_key(row.get("website"))
    rating = _number(row.get("rating"))
    reviews = _integer(row.get("review_count"))
    photos = _integer(row.get("profile_photo_signal_count"))
    rating_median = _number(benchmark.get("rating_median"))
    review_median = _number(benchmark.get("review_count_median"))
    photo_median = _number(benchmark.get("profile_photo_signal_median"))
    visual = visual_by_website.get(website) or visual_by_name.get(name.casefold()) or []

    strengths: list[str] = []
    gaps: list[str] = []
    opportunities: list[str] = []

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
        opportunities.append("Make existing trust signals and customer proof more prominent online.")

    photo_position = _relative(
        float(photos) if photos is not None else None,
        photo_median,
        stronger=1.5,
        weaker=0.5,
    )
    if photo_position == "stronger":
        strengths.append("Google Maps shows stronger visible photo/profile coverage than the local median.")
    elif photo_position == "weaker":
        gaps.append("Google Maps shows weaker visible photo/profile coverage than the local median.")
        opportunities.append("Improve recent, business-specific visual proof across the local profile and website.")

    if website:
        strengths.append("A business website is directly available from the local listing.")
    else:
        gaps.append("No business website was captured from the local listing.")
        opportunities.append("Create or reconnect a clear website destination from the local profile.")

    for issue in visual[:2]:
        noticed = _text(issue.get("what_we_noticed"))
        if noticed:
            gaps.append(f"Website evidence: {noticed}")
            issue_type = _text(issue.get("issue_type"))
            if issue_type == "mobile_overflow":
                opportunities.append("Improve the mobile presentation so the business is easier to use than nearby alternatives.")
            elif issue_type == "broken_link":
                opportunities.append("Remove the visible website dead end before using the site as a trust/conversion destination.")

    if review_position == "stronger" and visual:
        opportunities.insert(
            0,
            "The business already has strong customer proof; make the website presentation match that reputation.",
        )

    unique_opportunities: list[str] = []
    for item in opportunities:
        if item not in unique_opportunities:
            unique_opportunities.append(item)

    return {
        "result_rank": row.get("result_rank"),
        "business_name": name,
        "website": _text(row.get("website")),
        "source_url": _text(row.get("source_url")),
        "category": _text(row.get("category")),
        "signals": {
            "rating": rating,
            "review_count": reviews,
            "profile_photo_signal_count": photos,
            "rating_vs_local_median": rating_position,
            "review_volume_vs_local_median": review_position,
            "photo_signal_vs_local_median": photo_position,
        },
        "strengths": strengths,
        "competitive_gaps": gaps,
        "webify_opportunities": unique_opportunities[:3],
        "website_visual_evidence_count": len(visual),
    }


def _summary_html(benchmark: dict[str, object], contexts: list[dict[str, object]]) -> str:
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'><title>VERIDRA local competitive context</title>",
        "<style>body{font-family:Arial,sans-serif;max-width:1100px;margin:40px auto;padding:0 20px;color:#202124}section{border-top:1px solid #ddd;padding:22px 0}table{border-collapse:collapse}td,th{padding:7px 12px;border:1px solid #ddd;text-align:left}li{margin:7px 0}.muted{color:#68707a}</style></head><body>",
        "<h1>Local Competitive Context</h1>",
        f"<p>Businesses compared: <strong>{benchmark['business_count']}</strong>. This is relative commercial context, not a global score.</p>",
        "<table><tr><th>Signal</th><th>Local median</th><th>Coverage</th></tr>",
        f"<tr><td>Google rating</td><td>{html.escape(str(benchmark.get('rating_median') or '—'))}</td><td>{benchmark['rating_coverage']}</td></tr>",
        f"<tr><td>Review count</td><td>{html.escape(str(benchmark.get('review_count_median') or '—'))}</td><td>{benchmark['review_count_coverage']}</td></tr>",
        f"<tr><td>Photo/profile signal</td><td>{html.escape(str(benchmark.get('profile_photo_signal_median') or '—'))}</td><td>{benchmark['profile_photo_signal_coverage']}</td></tr></table>",
        "<p class='muted'>Review quality in this version means measurable reputation strength (rating and review volume). Review text sentiment is not inferred because review bodies are not collected by this experiment.</p>",
    ]
    for context in contexts:
        parts.append(f"<section><h2>{html.escape(_text(context.get('business_name')))}</h2>")
        signals = context.get("signals") if isinstance(context.get("signals"), dict) else {}
        parts.append(
            f"<p>Rating: <strong>{html.escape(str(signals.get('rating') or '—'))}</strong> · Reviews: <strong>{html.escape(str(signals.get('review_count') or '—'))}</strong> · Website visual findings: <strong>{context.get('website_visual_evidence_count', 0)}</strong></p>"
        )
        for title, key in (
            ("Strengths", "strengths"),
            ("Competitive gaps", "competitive_gaps"),
            ("Webify opportunities", "webify_opportunities"),
        ):
            values = context.get(key)
            parts.append(f"<h3>{title}</h3><ul>")
            if isinstance(values, list) and values:
                parts.extend(f"<li>{html.escape(_text(value))}</li>" for value in values)
            else:
                parts.append("<li>No strong relative signal from the available evidence.</li>")
            parts.append("</ul>")
        parts.append("</section>")
    parts.append("</body></html>")
    return "".join(parts)


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    discovery = args.input or _latest(args.downloads, "VERIDRA_DISCOVERY_*.zip")
    if discovery is None or not discovery.is_file():
        raise FileNotFoundError("No discovery evidence ZIP was found.")
    visual = args.visual_input or _latest(args.downloads, "VERIDRA_VISUAL_EVIDENCE_STRICT_*.zip")
    rows = _load_discovery(discovery)
    if not rows:
        raise ValueError("Discovery evidence contains no businesses.")
    visual_by_name, visual_by_website = _load_visual(visual)
    benchmark = build_benchmark(rows)
    contexts = [
        _context_for(row, benchmark, visual_by_name, visual_by_website)
        for row in rows
    ]

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    label = _safe_name(args.label).upper()
    output = args.output_directory / f"VERIDRA_COMPETITIVE_{label}_{stamp}.zip"
    args.output_directory.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_discovery": discovery.name,
        "source_visual_evidence": visual.name if visual is not None else None,
        "businesses_compared": len(contexts),
        "comparison_method": "relative cohort medians; no global score",
        "review_quality_method": "rating + review volume only; review text is not collected",
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
            "# VERIDRA Local Competitive Context\n\nRead-only relative comparison for a local search cohort. It does not send outreach, persist prospect state, or produce a universal score. Review-text sentiment is intentionally excluded until review bodies are collected reliably.\n",
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
                "input": str(discovery),
                "visual_input": str(visual) if visual is not None else None,
                "output": str(output),
                "businesses_compared": len(contexts),
                "rating_coverage": benchmark["rating_coverage"],
                "review_count_coverage": benchmark["review_count_coverage"],
                "profile_photo_signal_coverage": benchmark["profile_photo_signal_coverage"],
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
