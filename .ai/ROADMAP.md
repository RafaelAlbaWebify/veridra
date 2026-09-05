# VERIDRA Roadmap

Status values: `COMPLETE`, `ACTIVE`, `NEXT`, `LATER`, `OPTIONAL`, `REJECTED`.

## Completed

### R-001 — Core bounded assessment engine — COMPLETE
Dependencies: none.
Acceptance: public-target safety boundaries, crawl/evidence behavior and deterministic audit tests pass.
Evidence: source/tests + CI.

### R-002 — Multi-tenant agency/commercial workflow — COMPLETE
Acceptance: authenticated tenant-qualified prospect/lead/project/report/remediation/monitoring workflow passes synthetic browser acceptance.
Evidence: CI commercial/browser acceptance.

### R-003 — Synthetic full business lifecycle — COMPLETE
Acceptance: supported UI completes reply/discovery/proposal/terms/payment gate/onboarding/project/assessment/remediation/change control/acceptance/handoff/recurring/payment failure+recovery/renewal/cancellation, including restart and backup/restore.
Evidence: merge #295, CI run 33895989746.
Limit: synthetic only.

### R-104 — M1 recurring/exception operating controls — COMPLETE
Dependencies: R-003, frozen Presence Care scope/SOP/payment/access/change controls.
Acceptance: monthly report, additional-work quotation, complaint/issue record and renewal/service-change record created, governed and registered against existing operating boundaries.
Evidence: Webify Client Operations Document Register items 20–23.
Limit: templates are not real-customer proven and do not replace legal/provider approval.

### R-105 — M1 access/SOW business reconciliation — COMPLETE
Dependencies: R-104 and frozen access/change/payment/data boundaries.
Acceptance: Digital Asset Access Authorization and SOW/Change Order align with least privilege, MFA/secret handling, safe form testing, material-change approval, payment authority, backup/rollback, verification, sensitive-data and third-party/tax operating rules.
Evidence: current controlled Drive documents + Document Register.
Limit: business reconciliation only; legal/tax/jurisdiction review and real dry-run evidence remain required.

### R-106 — Ireland first-market tax/invoice operating reference — COMPLETE
Dependencies: payment/invoice operating policy and current Revenue guidance.
Acceptance: Ireland operator reference records VAT-invoice fields, customer-status evidence, reverse-charge/business-customer decision gate, electronic-invoice audit trail, retention, Stripe invoice validation, sales-ledger evidence and correction path without inferring transaction tax treatment.
Evidence: `WEBIFY — Ireland First-Market Tax & Invoice Operating Reference`, current Irish Revenue guidance and controlled company VAT records.
Limit: actual first-customer VAT/tax treatment, Stripe invoice output and Stripe→bank→ledger reconciliation remain unverified.

## Active

### R-100 — M1 business-ready operating layer — ACTIVE (~90%)
Dependencies: R-003.
Acceptance: service scope/SOP/payment/access/change/report/offboarding/support controls complete; customer-facing legal documents reconciled and approved where required; tax/privacy/provider boundaries explicit.
Current remaining work: qualified production approval/review of MSA, Order Form, DPA, Access Authorization and SOW/Change Order where required; actual first-customer tax treatment when customer/transaction is known; final production provider/subprocessor posture; legal/jurisdiction/transfer/sector decisions where applicable; clean approved customer-facing release set.
Evidence required: repository/controlled document register + professional review where applicable + actual provider/transaction evidence.

### R-110 — First-customer readiness master gate (#296) — ACTIVE
Dependencies: R-100, R-200, R-300, R-400, R-500.
Acceptance: all #296 final acceptance criteria pass.
Evidence required: public origin, external providers, full dry run, human review.

## Next

### R-200 — M2 production infrastructure — NEXT
Dependencies: R-100 sufficiently stable.
Acceptance: hosted environment, DNS/TLS, durable storage, web+worker supervision, logs/health, scheduled backup/ops checks and restore proof.
Evidence: deployed commit, preflight output, restore evidence.

### R-300 — M3 provider-ready — NEXT
Acceptance: real SMTP verified; Stripe test products/prices/Checkout/Portal/webhook/subscription lifecycle verified; invoice/accounting reference path exercised.

### R-400 — M4 production validation — NEXT
Acceptance: `veridra-production-preflight --require-stripe` passes and `veridra-deployment-check --origin ...` passes against actual HTTPS origin.

### R-500 — M5 full external dry run — NEXT
Acceptance: actual deployed services and external providers complete the #296 synthetic-customer flow with no DB/store shortcuts and no unresolved P0/P1 blocker.

### R-600 — M6 human operator acceptance — NEXT
Acceptance: Rafael manually performs the flow and approves usability/process evidence.

## Later

### R-700 — First controlled prospect — LATER
Dependencies: #284/#296 approved.
Acceptance: 3–5 manually verified high-quality prospects; no bulk outreach.

### R-800 — First paying activation — LATER
Acceptance: signed/accepted terms, real activation payment, authorized access, delivery and customer acceptance.

### R-900 — First recurring cycle — LATER
Acceptance: recurring monitoring/report and successful recurring charge/payment reconciliation.

### R-1000 — Fully operative / economics proven — LATER
Acceptance: at least one real paying customer completes activation plus recurring cycle; no unresolved P0/P1; economics/time/support measured.

## Optional
- broader verticals/countries only after first-customer evidence;
- shared/multi-writer persistence only if scale requires it;
- broader market-data integrations where commercially justified.

## Rejected / out of scope
See `.ai/REJECTED_APPROACHES.md`.
