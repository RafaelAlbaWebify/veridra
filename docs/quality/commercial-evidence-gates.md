# VERIDRA commercial evidence gates (first real-world validation)

Status: **NOT CERTIFIED**. Canonical local synthetic E2E passing does not certify audit accuracy, prospect fit, or sales effectiveness. No outreach, exports of private data, or scans of unauthorized targets are approved by this document.

## Gate A: audit reliability — independently labelled benchmark

Use 12 explicitly authorized or locally served fixture sites, with a frozen URL list, date, fetch scope, and expected findings established **before** running VERIDRA. Include responsive/rendered pages, multiple languages, redirect chains, duplicate titles, legitimate noindex pages, robots restrictions, inaccessible subpages, external contact/legal URLs, and no JSON-LD.

For every issue, store: site/URL; rule ID; expected present/absent/unknown; captured raw evidence and HTTP status; actual VERIDRA status/severity; independent reviewer; discrepancy; disposition. Do not label a page as defective solely because a bounded crawl missed it.

Suggested release thresholds (initial targets, not achieved): >=90% precision on actionable findings, >=85% recall on detectable seeded defects, **zero** critical false claims (security breach, legal noncompliance, guaranteed AI ranking/revenue); >=95% reproducibility on repeated local fixtures. Report per-rule precision and recall, denominators and unknowns. Manual review is mandatory for accessibility, legal and business-impact judgments.

### Known hypotheses to test before changing code
- `commercial_crawl_findings.py`: `crawl.trust-pages` classifies pages by URL path suffix and treats categories not found in a **bounded** crawl as missing. Exercise a fixture where /privacy exists but crawl depth excludes it; outcome should be `not observed within scope`, not asserted absence.
- `commercial_crawl_findings.py`: `crawl.structured-data-coverage` infers a deficiency when no crawled page has a JSON-LD script tag; legitimate alternative structured-data formats and irrelevant page types should not be described as proven defects.
- `prospect_opportunity.py`: `website_evidence_kind` calls any non-booking external URL `external_website`. Test links to social profiles/marketplaces versus verified owned domains; avoid claiming verified site ownership.

## Gate B: prospect quality — blind, labelled cohort

Build a **local-only** sample of 30 candidates across three sectors/areas, including missing-web cases, strong established websites, booking-only listings, duplicates, closed businesses, franchises and low-review businesses. Keep raw discovery evidence and timestamps; redact personal data.

Before inspecting score bands, have a reviewer independently label each on:
1. Operating business verified? (yes/no/unknown)
2. Owned website verified? (yes/no/unknown)
3. Remediable Webify service need evidenced? (yes/no/unknown)
4. Commercial fit (service geography, sector, estimated scope) (yes/no/unknown)
5. Buyer/decision-maker and budget **known**? (yes/no/unknown; do NOT infer from reviews)

Measure Precision@10 for verified, actionable opportunities; duplicate rate; unverifiable rate; and agreement between human labels and ranking. Initial goal: >=8 of top 10 meet 1-4, 0 closed/duplicate profiles in top 10, with any unknown explicitly flagged. Commercial willingness-to-pay requires actual discovery/replies under approved outreach processes and is not measured by this offline score.

## Gate C: reports — actionable, ethically saleable output

Produce 5 anonymized reports from benchmark sites, including 1 with few/no issues. Two reviewers independently score each (0=missing, 1=partial, 2=complete) for:
- Traceable exact URL, observation, and evidence
- Scope/unknowns and clear separation of observed facts from inference
- Fix steps with verification method and affected pages
- Risk/severity proportionate to evidence; no invented revenue/AI/security claims
- Clear Webify service scope, proposed deliverable, owner, and next step
- Readability and accessibility of PDF; no broken tables, pages, branding or untranslated labels

Release target: >=10/12 for each report, no score 0 on traceability or honest limitations, no misleading claims, and manual visual inspection of exported PDFs. This measures report quality **not sales conversion**. Actual conversion needs consent-based outreach and an outcome cohort.

## Execution and evidence discipline

1. Freeze sample/fixtures and independent gold labels before collecting VERIDRA outputs.
2. Run locally or on authorized targets only; never send synthetic mail externally.
3. Keep raw captures, tool version/commit, time, statuses, screenshots, extracted report text and reviewer notes in a **private** evidence location outside the repository if they contain identifiers.
4. Calculate false positives/negatives and top-10 precision; fix highest-impact errors first with regression fixtures.
5. Repeat benchmark after each PR. Require both existing CI and this validation before making customer-facing claims.
6. Publish only aggregated non-sensitive results. Mark each gate PASS/FAIL/INSUFFICIENT EVIDENCE. Do not turn unobserved facts into defects or use E2E pass as evidence of market fit.

## Pending code changes (ordered)
- Make missing-vs-not-observed outcomes scope-aware for trust pages and JSON-LD, with focused regression tests.
- Separate verified owned websites, third-party booking pages and social links in discovery; revise qualification evidence.
- Require per-finding proof and review status before inserting a claim into client-facing sales material.
- Add a local evaluation runner consuming labelled fixture JSON and emitting per-rule confusion counts, Precision@10 and report-review scoring.
