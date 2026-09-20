from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import httpx


SUPPORTED = {
    "accessibility.document-language",
    "accessibility.duplicate-ids",
    "accessibility.form-labels",
    "accessibility.heading-order",
    "accessibility.image-alt",
}


@dataclass
class Signals:
    language: str = ""
    ids: list[str] = field(default_factory=list)
    headings: list[int] = field(default_factory=list)
    images_missing_alt: int = 0
    controls_unlabelled: int = 0


class IndependentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.signals = Signals()
        self._labels_for: set[str] = set()
        self._controls: list[tuple[str, bool, bool]] = []
        self._label_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        data = {key.casefold(): (value or "") for key, value in attrs}
        lowered = tag.casefold()

        if lowered == "html":
            self.signals.language = data.get("lang", "").strip()

        element_id = data.get("id", "").strip()
        if element_id:
            self.signals.ids.append(element_id)

        if lowered == "label":
            self._label_depth += 1
            target = data.get("for", "").strip()
            if target:
                self._labels_for.add(target)

        if lowered == "img" and "alt" not in data:
            self.signals.images_missing_alt += 1

        if lowered in {"input", "select", "textarea"}:
            if data.get("type", "").casefold() != "hidden":
                accessible_name = bool(
                    data.get("aria-label", "").strip()
                    or data.get("aria-labelledby", "").strip()
                    or data.get("title", "").strip()
                )
                wrapped = self._label_depth > 0
                self._controls.append((element_id, accessible_name, wrapped))

        if len(lowered) == 2 and lowered[0] == "h" and lowered[1].isdigit():
            level = int(lowered[1])
            if 1 <= level <= 6:
                self.signals.headings.append(level)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "label" and self._label_depth:
            self._label_depth -= 1

    def close(self) -> None:
        super().close()
        self.signals.controls_unlabelled = sum(
            not named
            and not wrapped
            and (not control_id or control_id not in self._labels_for)
            for control_id, named, wrapped in self._controls
        )


def _check(identifier: str, body: str) -> tuple[bool, dict[str, Any]]:
    parser = IndependentParser()
    parser.feed(body)
    parser.close()
    signals = parser.signals

    if identifier == "accessibility.document-language":
        bad = not signals.language
        return bad, {"language": signals.language or None}

    if identifier == "accessibility.duplicate-ids":
        duplicates = sorted(
            value for value, count in Counter(signals.ids).items() if count > 1
        )
        return bool(duplicates), {"duplicate_ids": duplicates[:20]}

    if identifier == "accessibility.form-labels":
        return signals.controls_unlabelled > 0, {
            "controls_unlabelled": signals.controls_unlabelled
        }

    if identifier == "accessibility.image-alt":
        return signals.images_missing_alt > 0, {
            "images_missing_alt": signals.images_missing_alt
        }

    if identifier == "accessibility.heading-order":
        skips = [
            [previous, current]
            for previous, current in zip(
                signals.headings,
                signals.headings[1:],
                strict=False,
            )
            if current > previous + 1
        ]
        return bool(skips), {
            "heading_sequence": signals.headings[:50],
            "detected_skips": skips[:20],
        }

    raise ValueError(f"Unsupported finding: {identifier}")


def _affected_urls(occurrences: list[dict[str, Any]]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for occurrence in occurrences:
        evidence = occurrence.get("evidence", {})
        if not isinstance(evidence, dict):
            continue
        values = evidence.get("affected_urls", [])
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, str) and value not in seen:
                seen.add(value)
                urls.append(value)
    return urls


def _read(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "family_index",
        "finding_id",
        "severity",
        "title",
        "occurrence_count",
        "business_count",
        "urls_expected",
        "urls_fetched",
        "urls_confirmed",
        "urls_contradicted",
        "urls_inconclusive",
        "independent_state",
        "independent_details_json",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--review-directory",
        type=Path,
        default=Path("artifacts/smb-validation/human-validation"),
    )
    args = parser.parse_args(argv)

    families = _read(args.review_directory / "family_finding_review.csv")
    results: list[dict[str, Any]] = []

    with httpx.Client(
        follow_redirects=True,
        timeout=15.0,
        headers={"User-Agent": "VERIDRA-Independent-Validation/1.0"},
    ) as client:
        for row in families:
            identifier = row.get("finding_id", "")
            if identifier not in SUPPORTED:
                continue

            try:
                occurrences = json.loads(row.get("occurrences_json", "[]"))
            except json.JSONDecodeError:
                occurrences = []
            if not isinstance(occurrences, list):
                occurrences = []

            urls = _affected_urls(
                [item for item in occurrences if isinstance(item, dict)]
            )
            details: list[dict[str, Any]] = []
            confirmed = 0
            contradicted = 0
            inconclusive = 0

            for url in urls:
                try:
                    response = client.get(url)
                    response.raise_for_status()
                    bad, evidence = _check(identifier, response.text)
                    if bad:
                        state = "confirmed"
                        confirmed += 1
                    else:
                        state = "contradicted"
                        contradicted += 1
                    details.append(
                        {
                            "url": str(response.url),
                            "state": state,
                            "status_code": response.status_code,
                            "evidence": evidence,
                        }
                    )
                except Exception as exc:
                    inconclusive += 1
                    details.append(
                        {
                            "url": url,
                            "state": "inconclusive",
                            "error": str(exc),
                        }
                    )

            fetched = confirmed + contradicted
            if urls and contradicted == 0 and inconclusive == 0:
                independent_state = "confirmed"
            elif contradicted > 0:
                independent_state = "mixed_or_contradicted"
            else:
                independent_state = "inconclusive"

            results.append(
                {
                    "family_index": row.get("family_index", ""),
                    "finding_id": identifier,
                    "severity": row.get("severity", ""),
                    "title": row.get("title", ""),
                    "occurrence_count": row.get("occurrence_count", ""),
                    "business_count": row.get("business_count", ""),
                    "urls_expected": len(urls),
                    "urls_fetched": fetched,
                    "urls_confirmed": confirmed,
                    "urls_contradicted": contradicted,
                    "urls_inconclusive": inconclusive,
                    "independent_state": independent_state,
                    "independent_details_json": json.dumps(
                        details,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                }
            )

            print(
                f"[Veridra] {identifier}: {independent_state} "
                f"({confirmed} confirmed, {contradicted} contradicted, "
                f"{inconclusive} inconclusive)"
            )

    output = args.review_directory / "independent_technical_verification.csv"
    _write(output, results)
    print(
        f"[Veridra] Independent technical verification written to: {output}"
    )
    print(
        f"[Veridra] Supported families cross-checked: {len(results)} / {len(families)}"
    )
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
