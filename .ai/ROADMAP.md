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

### R-203 — Cloud-host provider experiment — OPTIONAL / RETIRED FROM GATE
Hetzner Cloud EU / Nuremberg was previously selected for a hypothetical hosted deployment.
Current operator-track decision: the Webify operator runtime remains local on Rafael's Windows PC. No VM is required for that track. The separate hosted VERIDRA SaaS track uses H-000…H-600 and its single-host deployment boundary.

### R-204 — Optional cloud backup experiment — OPTIONAL
Backblaze B2/restic implementation is retained as optional future research.
Current #296 requires a verified backup plus an independent operator-controlled second copy; paid cloud backup is not mandatory.

### R-205 — Public DNS/TLS deployment boundary — OPTIONAL / NOT REQUIRED
Public application DNS/TLS/Caddy is not part of the canonical Webify operator / Presence Care architecture; that runtime remains loopback-only on the operator PC. The hosted VERIDRA SaaS track separately requires HTTPS/Caddy acceptance under H-500.

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

## Hosted VERIDRA SaaS track

The hosted product is now an active separate business/product track under D-012. It does not inherit operator readiness claims.

### H-000 — SaaS resurrection audit — COMPLETE
Acceptance:
- retained hosted modules classified KEEP / REWORK / MISSING / REMOVE;
- operator and hosted runtime boundaries separated;
- entitlement/quota/isolation bypasses closed;
- persistent audit document current;
- repository CI green.

Evidence: `.ai/SAAS_RESURRECTION_AUDIT.md`; CI run 36990112480 on head 4250c769 completed successfully.

### H-100 — Commercial integrity baseline — COMPLETE
Acceptance:
- signup/login/workspace/plan path coherent;
- audit/project quotas enforced;
- white-label/report/PDF entitlements enforced;
- monitoring metered;
- embedded lead forms tenant-bound and metered;
- lead source evidence tenant-scoped;
- team seats enforced;
- downgrade/recovery paths do not dead-end.

Evidence: `.ai/HOSTED_H1_ACCEPTANCE.md`; CI run 36990700714 on head f65f4caa completed successfully.

### H-200 — Commercial product UX — COMPLETE
Acceptance:
- entitlement-aware locked/upgrade/recovery states;
- hosted navigation exposes the agency audit product rather than internal Webify sales/customer workflows;
- quota/capacity failures are anticipated in normal browser flows;
- embed-form setup and allowed-origin postback are usable;
- lead pipeline exposes source provenance and project-native conversion;
- team/billing recovery states are understandable.

Evidence: `.ai/HOSTED_H2_ACCEPTANCE.md`; CI run 36998742301 on head fd31827e completed successfully.

### H-250 — Report polish — COMPLETE
Acceptance:
- reusable saved profiles gain practical section presets rather than a second persistence model;
- navigable table of contents;
- useful bounded-data summary visualization;
- deliberate print/page-break behavior for long reports;
- HTML preview and PDF regression coverage remain aligned.

Evidence: `.ai/HOSTED_H3_ACCEPTANCE.md`; CI run 37001235636 on code head 09cf905f completed successfully.

### H-300 — Audit scale/job model — COMPLETE
Acceptance:
- larger crawl work has a durable worker path outside long-lived HTTP requests;
- explicit progress/job/leasing/retry state;
- page-budget/concurrency and usage-reservation enforcement;
- deterministic 500-page workload proven in both crawler and durable worker;
- customer-facing Deep profile intentionally remains capped at 100 pages.

Evidence: `.ai/HOSTED_H4_ACCEPTANCE.md`; CI run 37005555931 on code head b730c7af completed successfully.

### H-350 — Lead-generation product polish — ACTIVE
Acceptance:
- embedded form visual branding reuses tenant white-label profile safely;
- setup/origin/rate-limit/plan guidance remain regression-protected;
- lead provenance and conversion/report attribution remain tenant-scoped;
- no duplicate branding persistence model.

### H-400 — Real provider lifecycle — LATER
Acceptance:
- SMTP real sender;
- Stripe test Checkout/webhook/upgrade/downgrade/failure/portal/cancellation;
- provider reconciliation evidence.

### H-500 — Hosted deployment acceptance — LATER
Acceptance:
- actual HTTPS single-host stack;
- end-to-end signup → audit/report → lead/project → monitoring;
- off-host backup and isolated restore;
- provider reconciliation after restore;
- human acceptance.

### H-600 — Controlled hosted commercial launch — LATER
Dependencies: H-000 through H-500 complete; pricing/legal/product-launch decisions approved.

**No hosted launch percentage is currently authoritative.**

## Active

### R-100 — M1 business-ready operating layer — ACTIVE (~95%)
Remaining: qualified production approval of customer legal controls where required; actual first-customer tax treatment; actual provider/entity/location/transfer evidence; clean approved release set.

### R-110 — First-customer readiness master gate (#296) — ACTIVE
Acceptance: real-SMB value, production, external-provider, dry-run and human evidence pass. #284 remains the final no-outreach approval gate.

### R-150 — Real-SMB digital presence validation (#297) — COMPLETE
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

Operability weight: **10 points**, current credit **10/10**. #297 closed completed on 2026-09-25 with 11/11 evidence-sufficient human reviews, four shadow deliveries, a human-accepted customer-report direction and a CONDITIONAL recurring-value decision.

### R-200 — M2 operator-local production runtime — ACTIVE
Acceptance: hardened Windows-local profile on Rafael's actual PC; loopback-only bind; durable state; web/monitoring supervision; protected logs; verified backup; independent second copy; isolated restore.
No VPS, public DNS/TLS, Caddy or provider firewall is required.
Current real-world credit: 0 until actual-workstation evidence exists.

### R-300 — M3 provider/accounting readiness — ACTIVE
Acceptance: real Brevo account/sender identity-email/report flows required by the local operator workflow; Stripe sandbox Presence Care activation + subscription/invoice/management/failure/recovery/cancellation; real Stripe → accounting → VERIDRA reconciliation; actual provider transfer/tax evidence.
Current real-world credit: 0 until external evidence exists.

## Next

### R-400 — M4 operator-local production validation — NEXT
A hardened Windows-local preflight and browser/operator acceptance must pass against the actual loopback deployment. The public HTTPS deployment checker is not a gate.

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

## Readiness measurement

The prior single weighted VERIDRA operability percentage is **withdrawn as a global project measure**.

Reason: operator-local first-customer readiness and hosted SaaS launch readiness now have different architectures, providers and acceptance gates.

- Use #279/#284/#296 evidence for the Webify operator track.
- Use H-000…H-600 and `.ai/SAAS_RESURRECTION_AUDIT.md` for the hosted product.
- Do not combine them into one percentage until an explicit shared measurement model is approved.

## Optional
- broader verticals/countries only after first-customer evidence;
- shared/multi-writer persistence only if scale requires it;
- custom domains, report-open analytics and broader enterprise SaaS features only after hosted MVP evidence;
- dedicated accounting SaaS only if justified after first-customer process evidence;
- second independent backup provider only if measured risk justifies it;
- HTTP proxy/CDN/edge layer only if measured need justifies added processing/privacy complexity;
- broader market-data integrations where commercially justified by #297 evidence.

## Rejected / out of scope
See `.ai/REJECTED_APPROACHES.md`.
