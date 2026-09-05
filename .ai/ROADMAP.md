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

### R-202 — Worker and local backup supervision — COMPLETE (IMPLEMENTED)
Acceptance: bounded monitoring worker uses no-overlap systemd scheduling; backup automation quiesces worker/web, invokes the existing verified `veridra-backup` CLI, recovers services on exit and is scheduled by systemd; repository tests enforce these controls.
Limit: no real host archive or restore has yet been produced.

### R-203 — First-host provider selection — COMPLETE (SELECTION ONLY)
Decision: Hetzner Cloud EU is the production-intended first-host path, with Nuremberg (`nbg1`) preferred initially. Terraform and the provider-neutral application bundle preserve the option to change hosting provider.
Evidence: `infra/hetzner/`, `docs/operations/first-host-acceptance.md`, Webify Subprocessor Register.
Limit: no Hetzner account/project/VM is deployed or production approved.

### R-204 — Independent encrypted off-host backup path — COMPLETE (ARCHITECTURE)
Decision: Backblaze B2 EU Central (Amsterdam) is the production-intended independent off-host DR destination. A separate systemd service replicates the newest verified local `veridra-*.zip` only after the quiesced local backup has completed and application services recover; restic client-side encryption is mandatory and B2 is accessed through its S3-compatible API.
Evidence: `docs/operations/offhost-backup-provider.md`, `deployment/offhost-backup-run.sh`, `deployment/offhost-backup.env.example`, `deployment/systemd/veridra-offhost-backup.service`, Webify Subprocessor Register.
Limit: no real B2 account/bucket, encrypted remote snapshot or remote-to-isolated restore exists yet.

### R-301 — Transactional email provider selection — COMPLETE (SELECTION ONLY)
Decision: Brevo is the production-intended first transactional-email/SMTP provider.
Evidence: `docs/operations/transactional-email-provider.md`, current official provider research and Webify Subprocessor Register.
Limit: no real Brevo account, sender authentication, DPA/security review or public-origin delivery has been externally verified.

### R-302 — Webify client-billing boundary — COMPLETE (ARCHITECTURE)
Decision: Stripe is the external authority for Webify Presence Care client billing; VERIDRA mirrors authoritative invoice/payment references and state through the agency recurring-service workflow. The existing `free/solo/professional/agency` Stripe adapter is only for separate VERIDRA workspace/SaaS billing and remains disabled for the first Webify operator deployment.
Evidence: `docs/operations/webify-client-billing-boundary.md`, `src/veridra/recurring_service.py`, agency recurring-service UI.
Limit: real Stripe sandbox Presence Care resources and accounting reconciliation are not yet externally verified.

### R-303 — Sales/billing reconciliation ledger — COMPLETE (OPERATING STRUCTURE)
Decision: `WEBIFY — Sales & Billing Reconciliation Ledger` is the controlled internal Stripe → Webify accounting/sales record → VERIDRA reconciliation sheet for the first-customer path.
Acceptance: native Google Sheet exists in `05 — Billing, Subscription & Payment Recovery`; authoritative provider/accounting/VERIDRA reference columns, payment states, tax-treatment evidence, reconciliation formula, validations and synthetic activation/monthly seed rows are implemented and verified.
Evidence: Drive spreadsheet `1-UIbvId7GA9yvqXsi3Y3ZJn8fJJWoki63zHqzrJaK1g`; Client Operations Document Register item 25; Subprocessor Register accounting entry.
Limit: synthetic seed only. It is not a substitute for statutory books or professional accounting/tax requirements, and no real Stripe sandbox transaction has yet been reconciled.

## Active

### R-100 — M1 business-ready operating layer — ACTIVE (~90%)
Remaining: qualified production approval of customer legal controls where required; actual first-customer tax treatment; final provider/subprocessor posture; applicable jurisdiction/transfer/sector decisions; clean approved release set.

### R-110 — First-customer readiness master gate (#296) — ACTIVE
Acceptance: all #296 final acceptance criteria pass with public-origin/provider/dry-run/human evidence.

### R-200 — M2 production infrastructure — ACTIVE
Dependencies: R-201/R-202/R-203/R-204 implemented/selected.
Acceptance: real hosted environment; public DNS/TLS; provider firewall; durable storage proven; web+worker supervision active; logs/health operational; scheduled local application backup produces verified archives; client-side-encrypted independent off-host copy succeeds; remote snapshot can be restored into an isolated environment and then passes the normal VERIDRA restore/acceptance procedure.
Current boundary: compute/runtime/local-backup/off-host tooling and provider choices are defined; no external host/B2 evidence yet.
Evidence required: Hetzner host evidence, exact deployed commit, health checks, local archive metadata, B2 EU region/account/bucket evidence, encrypted remote snapshot ID, remote-to-isolated restore result.

### R-300 — M3 provider-ready — ACTIVE
Dependencies: R-301/R-302/R-303 plus frozen Webify payment/invoice policy.
Acceptance: real Brevo SMTP account/sender/domain configuration reviewed and verified; signup verification/password reset/invitation delivery succeeds from the actual public origin; real Stripe sandbox Presence Care business-billing resources exercise activation payment, monthly subscription, invoice, portal/management path, payment failure/recovery and cancellation; authoritative provider references are reconciled through the controlled sales/billing ledger and mirrored through supported VERIDRA agency UI; invoice/accounting path is validated for the actual transaction.
Current boundary: provider/accounting structure exists, but Brevo and Stripe remain not externally verified and the ledger contains synthetic seed rows only.
Evidence required: provider account/configuration evidence, DPA/subprocessor/security review, delivery/billing lifecycle evidence, real ledger rows and accounting/tax reconciliation evidence.

## Next

### R-400 — M4 production validation — NEXT
Acceptance for the Webify operator deployment: standard `veridra-production-preflight` has no critical failures and `veridra-deployment-check --origin ...` passes against the actual HTTPS origin. Webify client Stripe billing is validated separately under R-300; `--require-stripe` applies only to a separately approved VERIDRA SaaS/workspace-billing launch.

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
- VERIDRA workspace/SaaS commercialization only as a separate business decision with separate Stripe Prices/terms/acceptance;
- dedicated accounting SaaS only if justified after first-customer process evidence or professional accounting requirements;
- second independent backup provider/copy only if measured risk justifies it;
- broader market-data integrations where commercially justified.

## Rejected / out of scope
See `.ai/REJECTED_APPROACHES.md`.
