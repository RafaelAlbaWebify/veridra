# VERIDRA Roadmap

Status values: `COMPLETE`, `ACTIVE`, `NEXT`, `LATER`, `OPTIONAL`, `REJECTED`.

## Completed

### R-001 — Core bounded assessment engine — COMPLETE
Bounded public-target assessment and deterministic audit behavior pass repository verification.

### R-002 — Multi-tenant agency/commercial workflow — COMPLETE
Authenticated tenant-qualified commercial workflow passes synthetic browser acceptance.

### R-003 — Synthetic full business lifecycle — COMPLETE
Supported UI completes reply/discovery/proposal/terms/payment gate/onboarding/project/assessment/remediation/change control/acceptance/handoff/recurring/payment failure+recovery/renewal/cancellation, restart and backup/restore.
Evidence: merge #295, CI run 33895989746.
Limit: synthetic only.

### R-104 — M1 recurring/exception operating controls — COMPLETE
Monthly report, additional-work quotation, complaint/issue record and renewal/service-change control are governed and registered.

### R-105 — M1 access/SOW business reconciliation — COMPLETE
Access Authorization and SOW/Change Order align with least privilege, approval, payment, rollback, verification and sensitive-data rules.
Limit: not legal-production approved.

### R-106 — Ireland first-market tax/invoice operating reference — COMPLETE
Current Revenue requirements and transaction-validation gates are recorded without inferring actual customer VAT treatment.

### R-107 — EU transfer + dental healthcare operating gates — COMPLETE (OPERATING BASELINE)
Provider/workflow-level EU/EEA transfer mapping, adequacy/SCC decisioning and the first-customer dental/healthcare special-category-data/content boundary are defined and registered.
Limit: not legal/production approval.

### R-201 — Canonical single-host deployment bundle — COMPLETE (IMPLEMENTED)
One provider-neutral `deployment/` bundle owns Compose, Caddy, secret template and single-writer persistent topology.

### R-202 — Worker and local backup supervision — COMPLETE (IMPLEMENTED)
No-overlap worker scheduling and quiesced application backup use the existing verified backup CLI and are covered by repository tests.

### R-203 — First-host provider selection — COMPLETE (SELECTION ONLY)
Hetzner Cloud EU / Nuremberg (`nbg1`) is the production-intended first-host path.
Limit: no real VM deployed.

### R-204 — Independent encrypted off-host backup path — COMPLETE (ARCHITECTURE + TESTED IN CI)
Backblaze B2 EU Central via restic client-side encryption is implemented/tested as the independent off-host path.
Limit: no real B2 snapshot/restore evidence.

### R-205 — First-production DNS/TLS boundary — COMPLETE (ARCHITECTURE)
Retain the existing competent authoritative DNS provider; no extra HTTP proxy/CDN by default; Caddy terminates TLS on-host.
Limit: actual DNS/provider/hostname not externally verified.

### R-301 — Transactional email provider selection — COMPLETE (SELECTION ONLY)
Brevo is production-intended for transactional SMTP.
Limit: no real sender/domain/public-origin delivery evidence.

### R-302 — Webify client-billing boundary — COMPLETE (ARCHITECTURE)
Stripe is authoritative for Presence Care client billing; VERIDRA mirrors provider references/state. VERIDRA workspace/SaaS billing remains separate and disabled for the first Webify deployment.

### R-303 — Sales/billing reconciliation ledger — COMPLETE (OPERATING STRUCTURE)
Controlled Google Sheet exists for Stripe → Webify accounting/sales record → VERIDRA reconciliation.
Limit: synthetic seed only.

### R-304 — Manual prospect accessibility/international cleanup — COMPLETE
#291 and #283 closed with CI run 33947738399; stale Vigo experiment #202 retired as not planned.

## Active

### R-100 — M1 business-ready operating layer — ACTIVE (~95%)
Remaining: qualified production approval of customer legal controls where required; actual first-customer tax treatment; actual provider/entity/location/transfer evidence; clean approved release set.

### R-110 — First-customer readiness master gate (#296) — ACTIVE
Acceptance: real-SMB value, production, external-provider, dry-run and human evidence pass. #284 remains the final no-outreach approval gate.

### R-150 — Real-SMB digital presence validation (#297) — ACTIVE
Purpose: prove VERIDRA + Presence Care creates real SMB value, not merely synthetic technical correctness.

Initial market: Ireland.
Initial vertical: independent dental practices.
Hard rule: **public-data/no-contact only; REAL OUTREACH COUNT = 0.**

Protocol: `docs/validation/smb-digital-presence-validation.md`.
Current durable evidence:
- `evidence/smb-validation/ie-dental-cohort-v1.csv` — 25 real practices, all `no_contact=true`;
- `evidence/smb-validation/ie-dental-manual-ground-truth-seed-v1.csv` — manual comparator seed containing true business-facing and low-value calibration findings.

Acceptance:
1. 25–50 reproducible real Irish dental-practice cohort;
2. bounded VERIDRA public assessments over the cohort;
3. 10–15 manually validated businesses with true-positive, false-positive, material-miss, owner-understandable, commercial-relevance, Webify-remediability and operator-time metrics;
4. 3–5 no-contact shadow Presence Care deliveries;
5. explicit recurring-value decision for the Ireland €99/month model;
6. discovered product/offer gaps fixed, accepted or recorded as blockers.

Operability weight: **10 points**, current credit **0/10**. Creating the protocol/cohort alone earns no credit.

### R-200 — M2 production infrastructure — ACTIVE
Dependencies: R-201/R-202/R-203/R-204/R-205.
Acceptance: real hosted environment; DNS/TLS; provider firewall; durable state; worker supervision; health/logging; scheduled local backup; encrypted independent off-host snapshot; isolated restore.
Current real-world credit: 0 until evidence exists.

### R-300 — M3 provider/accounting readiness — ACTIVE
Acceptance: real Brevo account/sender/domain/public-origin identity email flows; Stripe sandbox Presence Care activation + subscription/invoice/management/failure/recovery/cancellation; real Stripe → accounting → VERIDRA reconciliation; actual provider transfer/tax evidence.
Current real-world credit: 0 until external evidence exists.

## Next

### R-400 — M4 production validation — NEXT
Standard `veridra-production-preflight` and `veridra-deployment-check --origin ...` must pass against the actual HTTPS deployment.

### R-500 — M5 integrated actual-provider dry run — NEXT
Deployed infrastructure/providers complete the #296 synthetic-customer lifecycle with no DB/store shortcuts, including real SMB-assessment/reporting behavior, Stripe→ledger→VERIDRA evidence and backup/restore evidence.

### R-600 — M6 human operator acceptance — NEXT
Rafael manually performs the actual-provider workflow and approves usability/process evidence.

## Later

### R-700 — First controlled prospect — LATER
Dependencies: #297 and #296 complete, #284 explicitly approved. No bulk outreach.

### R-800 — First paying activation — LATER
Accepted terms, real activation payment, authorized access, delivery and customer acceptance.

### R-900 — First recurring cycle — LATER
Recurring monitoring/report + successful recurring payment reconciliation + measured customer value/operator time.

### R-1000 — Fully operative / economics proven — LATER
At least one real paying customer completes activation plus recurring cycle; no unresolved P0/P1; economics/time/support measured.

## Weighted path to 100%
- Product engineering + synthetic lifecycle: 20%
- M1 business operating layer: 20%
- Real-SMB digital presence validation: 10%
- M2 production infrastructure: 12%
- M3 external providers/accounting: 8%
- M4 production validation: 8%
- M5 integrated actual-provider dry run: 8%
- M6 human operator acceptance: 4%
- first controlled prospect + paid activation: 5%
- first recurring customer cycle: 4%
- closure/economics/no unresolved P0/P1: 1%

Current weighted operability: **39/100**.

## Optional
- broader verticals/countries only after first-customer evidence;
- shared/multi-writer persistence only if scale requires it;
- VERIDRA workspace/SaaS commercialization only as a separate business decision;
- dedicated accounting SaaS only if justified after first-customer process evidence;
- second independent backup provider only if measured risk justifies it;
- HTTP proxy/CDN/edge layer only if measured need justifies added processing/privacy complexity;
- broader market-data integrations where commercially justified by #297 evidence.

## Rejected / out of scope
See `.ai/REJECTED_APPROACHES.md`.
