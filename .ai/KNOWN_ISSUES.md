# Known Issues

Unresolved items remain here until verified closed. GitHub issue state is authoritative for tracked issues.

## KI-297 — P0 — Real-SMB digital presence value not yet validated
Module: assessment/evidence + commercial product validation.
Description: VERIDRA has strong synthetic assessment/lifecycle evidence, but real Irish SMB digital-presence value, finding precision, material misses, owner-understandability, Webify-remediability, operator time and recurring Presence Care value have not yet been proven.
Reproduction: inspect GitHub #297 and `docs/validation/smb-digital-presence-validation.md`.
Status: OPEN / BLOCKING REAL-PROSPECT READINESS.
Current evidence: 25-practice no-contact Ireland dental cohort and a small manual ground-truth seed exist; VERIDRA-vs-ground-truth validation and shadow recurring delivery remain incomplete.
Workaround: none; do not infer product-market/service value from synthetic tests or infrastructure readiness.
Next: complete #297 phases B–E.

## KI-296 — P0 — Real-world first-customer readiness
Module: cross-project / production.
Description: deployment, external providers, legal/paperwork, accounting, SMB value validation, dry run and human approval not complete.
Reproduction: inspect GitHub #296 final acceptance checklist.
Status: OPEN / BLOCKING.
Workaround: none; do not contact real prospects.
Blocking effect: `real_prospect_ready=false`, `production_ready=false`.
Next: complete business, SMB-validation, deployment, provider, dry-run and human gates.

## KI-284 — P0 — Master no-outreach gate
Module: commercial release.
Description: complete business cycle and real-SMB value evidence must be approved again after real-world evidence.
Status: OPEN / BLOCKING.
Workaround: none.

## KI-205 — P3 — Password show/hide UX
Module: identity web.
Description: requested password visibility control not yet confirmed implemented.
Status: OPEN per issue history; explicitly non-blocking for the current first-customer readiness gate.

## Architectural debt
- AD-001 P2: single package contains many agency web modules; logical boundaries are not package-enforced.
- AD-002 P1: production infrastructure/provider choices are external and currently unverified.
- AD-003 P1: customer-facing legal/tax documents remain non-production-approved.
- AD-004 P1: assessment/product value still needs real-SMB precision/miss/recurring-value calibration under #297.

## Recently verified/retired
- #291 manual prospect accessible labels — CLOSED completed; all 9 controls have stable `for`/`id`; regression passes in CI run 33947738399.
- #283 Spain-specific manual country default — CLOSED completed; fresh form has no `ES` value; regression passes in CI run 33947738399.
- #202 Vigo commercial experiment — CLOSED not planned; superseded by Ireland-first Presence Care strategy and #284/#296/#297 gates.

Do not silently delete an issue because it is old; confirm code/runtime and close/update the corresponding GitHub issue.
