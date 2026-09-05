# Known Issues

Unresolved items remain here until verified closed. GitHub issue state is authoritative for tracked issues.

## KI-296 — P0 — Real-world first-customer readiness
Module: cross-project / production.
Description: deployment, external providers, legal/paperwork, accounting, dry run and human approval not complete.
Reproduction: inspect GitHub #296 final acceptance checklist.
Status: OPEN / BLOCKING.
Workaround: none; do not contact real prospects.
Blocking effect: `real_prospect_ready=false`, `production_ready=false`.
Next: complete R-100..R-600.

## KI-284 — P0 — Master no-outreach gate
Module: commercial release.
Description: complete business cycle must be approved again after real-world evidence.
Status: OPEN / BLOCKING.
Workaround: none.

## KI-291 — P2 — Manual prospect form labels not associated with controls
Module: acquisition/agency web.
Description: visible labels on `/agency/prospects/new` lack programmatic `for`/`id` association; Playwright label lookup and accessibility are affected.
Reproduction: use `get_by_label("Business name")` on form.
Status: OPEN.
Workaround: stable `name=` selectors in acceptance.
Next: add id/for and regression test.

## KI-283 — P2 — International prospect form carries Spain-specific default
Module: acquisition/agency web.
Description: stale `ES` default conflicts with international-first prospecting.
Status: OPEN per project issue history; verify current source before fixing.

## KI-205 — P3 — Password show/hide UX
Module: identity web.
Description: requested password visibility control not yet confirmed implemented.
Status: OPEN per issue history; verify current source before work.

## KI-202 — P3 — Stale Vigo experiment
Module: acquisition experiments.
Description: old local experiment is no longer aligned with current international focus.
Status: OPEN historical cleanup item; should not drive roadmap.

## Architectural debt
- AD-001 P2: single package contains many agency web modules; logical boundaries are not package-enforced.
- AD-002 P1: production infrastructure/provider choices are external and currently unverified.
- AD-003 P1: customer-facing legal/tax documents remain non-production-approved.

Do not silently delete an issue because it is old; confirm code/runtime and close/update the corresponding GitHub issue.