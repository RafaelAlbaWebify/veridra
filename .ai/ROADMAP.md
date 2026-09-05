# VERIDRA Roadmap

Status values: `COMPLETE`, `ACTIVE`, `NEXT`, `LATER`, `OPTIONAL`, `REJECTED`.

## Completed

### R-001 — Core bounded assessment engine — COMPLETE
Acceptance: bounded public-target assessment and deterministic audit behavior pass repository verification.

### R-002 — Multi-tenant agency/commercial workflow — COMPLETE
Acceptance: authenticated tenant-qualified commercial workflow passes synthetic browser acceptance.

### R-003 — Synthetic full business lifecycle — COMPLETE
Acceptance: supported UI completes reply/discovery/proposal/terms/payment gate/onboarding/project/assessment/remediation/change control/acceptance/handoff/recurring/payment failure+recovery/renewal/cancellation, restart and backup/restore.
Evidence: merge #295, CI run 33895989746.
Limit: synthetic only.

### R-104 — M1 recurring/exception operating controls — COMPLETE
Monthly report, additional-work quotation, complaint/issue record and renewal/service-change control are governed and registered.

### R-105 — M1 access/SOW business reconciliation — COMPLETE
Access Authorization and SOW/Change Order align with least privilege, approval, payment, rollback, verification and sensitive-data rules.
Limit: not legal-production approved.

### R-106 — Ireland first-market tax/invoice operating reference — COMPLETE
Current Revenue requirements and transaction-validation gates are recorded without inferring actual customer VAT treatment.

### R-201 — Canonical single-host deployment bundle — COMPLETE (IMPLEMENTED)
Acceptance: one provider-neutral `deployment/` bundle owns Compose, Caddy, secret template and single-writer persistent topology; redundant `deploy/vm/` path removed.
Limit: implementation is not deployment evidence.

### R-202 — Worker and backup supervision — COMPLETE (IMPLEMENTED)
Acceptance: bounded monitoring worker uses no-overlap systemd scheduling; backup automation quiesces worker/web, invokes the existing verified `veridra-backup` CLI, recovers services on exit and is scheduled by systemd; repository tests enforce these controls.
Limit: no real host archive or restore has yet been produced.

## Active

### R-100 — M1 business-ready operating layer — ACTIVE (~90%)
Remaining: qualified production approval of customer legal controls where required; actual first-customer tax treatment; final provider/subprocessor posture; applicable jurisdiction/transfer/sector decisions; clean approved release set.

### R-110 — First-customer readiness master gate (#296) — ACTIVE
Acceptance: all #296 final acceptance criteria pass with public-origin/provider/dry-run/human evidence.

### R-200 — M2 production infrastructure — ACTIVE
Dependencies: R-201/R-202 implemented.
Acceptance: real hosted environment; public DNS/TLS; provider firewall; durable storage proven across replacement; web+worker supervision active; logs/health operational; scheduled application backup produces archives; independent off-host copy exists; isolated restore succeeds.
Current boundary: code/tooling is ready enough to provision; no external host evidence yet.
Evidence required: provider/host evidence, exact deployed commit, health checks, backup archive metadata and isolated restore result.

## Next

### R-300 — M3 provider-ready — NEXT
Acceptance: real SMTP verified; Stripe test products/prices/Checkout/Portal/webhook/subscription lifecycle verified; invoice/accounting path exercised.

### R-400 — M4 production validation — NEXT
Acceptance: `veridra-production-preflight --require-stripe` and `veridra-deployment-check --origin ...` pass against actual HTTPS origin.

### R-500 — M5 full external dry run — NEXT
Acceptance: deployed services and external providers complete the #296 synthetic-customer flow with no DB/store shortcuts and no unresolved P0/P1 blocker.

### R-600 — M6 human operator acceptance — NEXT
Acceptance: Rafael manually performs the actual-provider flow and approves usability/process evidence.

## Later

### R-700 — First controlled prospect — LATER
Dependencies: #284/#296 approved. No bulk outreach.

### R-800 — First paying activation — LATER
Acceptance: accepted terms, real activation payment, authorized access, delivery and customer acceptance.

### R-900 — First recurring cycle — LATER
Acceptance: recurring monitoring/report plus successful recurring charge/payment reconciliation.

### R-1000 — Fully operative / economics proven — LATER
Acceptance: at least one real paying customer completes activation plus recurring cycle; no unresolved P0/P1; economics/time/support measured.

## Optional
- broader verticals/countries only after first-customer evidence;
- shared/multi-writer persistence only if scale requires it;
- broader market-data integrations where commercially justified.

## Rejected / out of scope
See `.ai/REJECTED_APPROACHES.md`.
