# Operability Gates

## Current computed state
- Development usable: **PASS**
- Internal testing ready: **PASS**
- External beta/testing ready: **FAIL**
- Real prospect ready: **FAIL**
- Production ready: **FAIL**
- Weighted real-world operability: **60%**
- Remaining to full operability: **40%**
- M1 business readiness: **~95%**
- Real-SMB digital presence validation: **COMPLETED / 10 of 10 weighted points earned**
- M2 operator-local runtime: **11/12 PROVEN ON ACTUAL WORKSTATION**
- REAL OUTREACH COUNT: **0**

Operability history:
- 33% → 36%: recurring/reporting/exception operating controls completed.
- 36% → 37%: Access Authorization and SOW/Change Order business-reconciled.
- 37% → 38%: Ireland first-market tax/invoice operating reference completed.
- 38% → 39%: EU/EEA transfer decisioning and Ireland-first dental/healthcare data/content operating boundaries completed.
- 39% → 40%: first no-contact real-SMB Ireland dental cohort run through VERIDRA; 20/25 full assessments succeeded and 5 target-acquisition failures were preserved as evidence.
- 40% → 41%: calibrated rerun improved full-assessment success to 22/25, structured remaining acquisition failures, reduced mixed-content false positives, improved strict frozen-seed recall from 0/5 to 1/5, and preserved the G-Dental negative control.
- 41% → 42%: post-#300 frozen-cohort rerun on 2026-09-06 produced 21/25 full assessments, 4 structured target-observation failures, and improved strict positive frozen-seed recall from 1/5 (20%) to 2/4 evaluable (50%) while preserving the G-Dental negative control at 100%.
- 42% → 43%: targeted post-fix real-site verification of Crown Dental Dublin succeeded 1/1 and emitted `content.opening-hours-consistency` as high-severity attention with two concrete cross-page Saturday conflicts (`10:00-5:30` vs `9:30-6:30pm`) and owner-confirmation-required evidence. This converts the remaining current Crown false negative into a real-site hit.
- 43% → 44%: final 2026-09-20 frozen 25-business rerun produced 22/25 successful assessments; after explicit Dublin site-drift and Crown evidence-location-drift adjudication, current positive recall is 3/3 (100%), the G-Dental negative control remains 1/1 (100%), and current material misses are zero. #298 is closed completed.

Repository implementation, CI and architecture work do **not** automatically increase real-world operability. DEPLOYED / EXTERNALLY VERIFIED / PRODUCTION APPROVED / REAL-CUSTOMER PROVEN states require separate evidence.

## Weighted path to 100%
- A Product engineering + synthetic lifecycle: **20%** — current 20/20.
- B M1 business operating layer: **20%** — current ~19/20 (~95%).
- C Real-SMB digital presence validation: **10%** — current 10/10.
- D M2 operator-local production runtime: **12%** — current 11/12 real-world credit.
- E M3 external providers/accounting: **8%** — current 0/8.
- F M4 production validation: **8%** — current 0/8.
- G M5 integrated actual-provider dry run: **8%** — current 0/8.
- H M6 human operator acceptance: **4%** — current 0/4.
- I First controlled prospect + paid activation: **5%** — current 0/5.
- J First recurring customer cycle: **4%** — current 0/4.
- K Closure/economics/no unresolved P0/P1: **1%** — current 0/1.

Total current weighted operability: **60/100**.

## Gate 1 — Development usable — PASS
Repository/package/application entrypoints exist and the current verified code baseline is green.

## Gate 2 — Internal testing ready — PASS
Latest fully verified repository evidence: commit `ba7dd173389a69dfe67b7e613f3c0b7fb4e7243b`, GitHub Actions run `35894403744`, success across the current full repository validation after Phase C evidence-sufficiency, conservative value-classification, local-presence and frozen-seed ground-truth updates. This baseline includes the Phase C evidence-bound email posture and visible location/map detection regressions.

## M1 — Business-ready operating layer — ACTIVE (~95%)
Operating scope, activation/recurring SOP, payment/access/change/reporting/support/offboarding, Ireland tax/invoice, EU/EEA transfer decisioning and dental/healthcare data/content boundaries are defined. Remaining blockers are qualified production approval where required, actual transaction tax treatment, exact production-provider/entity/location evidence and clean approved customer-facing release set.

## C — Real-SMB digital presence validation — COMPLETED (#297)
Purpose: prove that VERIDRA + Webify Presence Care creates credible, understandable, remediable and recurring value for real SMBs rather than only passing synthetic website tests.

Initial market: Ireland.
Initial vertical: independent dental practices.

### Real evidence now earned
Post-#300 frozen-cohort rerun on 2026-09-06:
- 21/25 full assessments succeeded;
- 4 structured target-observation failures: Village Dental TLS self-signed certificate, Lucan Dental DNS resolution, Shandon Dental DNS resolution, and Bandon Dental Care TLS self-signed certificate;
- frozen comparator: positive_evaluable=4, positive_hits=2, strict_positive_recall=0.50;
- Dublin City Dentist Sample Page now matches `content.placeholder-default`;
- MB Dental remains a correct `content.explicit-update-age` hit;
- G-Dental negative control remains correct at 1/1 (100%);
- Village Dental's stale-content and hours-conflict observations remain unevaluable because strict TLS verification correctly blocks content acquisition.

Dublin City Dentist's former literal `call phone number` observation is adjudicated as **site drift**, not a current VERIDRA false negative: the homepage URL is present in captured assessment evidence while the exact phrase is absent.

#300 bounded owner-facing crawl prioritization is **CLOSED / COMPLETED**.

Crown Dental's previous remaining miss was an analyzer problem, not crawl selection. The parser collapsed multiple schedules on the same page. The fix now preserves multiple distinct values and is fully green in CI at `897919d719af6fa86beec27419756c053449d991` / run `34002932809`.

Targeted real-site verification on 2026-09-06:
- archive `VERIDRA_PROSPECT_AUDITS_20260906_031518.zip`;
- Crown Dental Dublin only;
- 1/1 assessment success, 0 failures;
- `content.opening-hours-consistency` emitted as `attention` / `high`;
- 2 cross-page conflicts detected;
- observed Saturday difference `10:00-5:30` vs `9:30-6:30pm`;
- affected pages include `/general-treatments/for-nervous-patients/`, `/emergency-dental-treatment/`, and `/about-us/`;
- `owner_confirmation_required_before_change=true`.

Final frozen-cohort calibration on 2026-09-20:
- 22/25 full assessments succeeded;
- 3 structured target-observation failures remained: Village Dental TLS, Lucan Dental DNS, Bandon Dental TLS;
- historical frozen positive recall intentionally remains 2/4 evaluable (50%);
- current adjudicated positive recall is 3/3 (100%);
- current negative-control pass rate is 1/1 (100%);
- current material misses: none;
- Village Dental's two seed items remain acquisition-blocked under strict TLS verification;
- #298 is **CLOSED / COMPLETED**.

Corrected Phase C evidence chain on 2026-09-23:
- the calibration loop removed multiple demonstrated false-positive sources while preserving the frozen negative control;
- a stop rule now freezes analyzer calibration unless a demonstrated material false positive/false negative changes a business-level qualification/value decision or violates an evidence claim;
- the latest authoritative no-contact evidence is **SMB Real Validation #27 / run `35894403715`**, commit `ba7dd173389a69dfe67b7e613f3c0b7fb4e7243b`;
- 22/25 full assessments succeeded and the same 3 acquisition failures remain;
- the current frozen-seed positive metric is **3/4 = 75%**, after restoring Dublin City Dentist's currently visible `call phone number` placeholder expectation; the G-Dental negative control remains **100%**;
- the Phase C pack is now **202 attention findings / 41 families**;
- **11/12** selected businesses have sufficient business-review evidence; South Dublin Dental has 0 analyzable HTML pages in this run and is therefore **evidence-insufficient**, not a valid clean/no-opportunity case;
- the current mechanical Presence Care value classifier identifies **81 commercially relevant + Webify-remediable findings across those 11 evaluable businesses**, with at least 5 per business;
- AI-assisted spot review has recorded five material misses across the representative sample: Dublin placeholder copy, Fiacla demo contact data, Ballincollig hours conflict, Elmwood hours conflict, and Shandon stale event promotion;
- those misses remain part of Phase C quality evidence and are not being hidden by further analyzer tuning.

This still earns **5/10 C credit** and leaves total operability at **44%**. Phase C is not complete until reduced operator/human confirmation, per-business material-miss and validation-time evidence, and 3–5 no-contact shadow deliveries are completed.

### Remaining #297 validation sequence
1. expand manual validation to 10–15 representative businesses and compute true-positive/false-positive/material-miss/owner-understandable/commercial-value/Webify-remediable/operator-time metrics;
2. run 3–5 no-contact shadow Presence Care deliveries;
3. measure activation work, monthly-allowance fit, separately quoted work and plausible recurring-cycle value;
4. make an explicit evidence-backed recurring-value decision for the Ireland €99/month model.

Hard rule: sampled businesses are **not outreach targets during this track**. Do not contact them, submit forms, authenticate, modify systems or bypass TLS validation.

## M2 — Operator-local production runtime — ACTIVE, real-workstation evidence absent
The canonical host is Rafael's Windows PC. VERIDRA remains loopback-only and is not intended to be Internet-facing.

No M2 real-world credit is granted until evidence proves on the actual workstation:
- hardened operator-local profile distinct from ordinary development mode;
- loopback-only binding;
- durable state;
- web and monitoring supervision;
- protected diagnostics/logs;
- scheduled/controlled backup;
- independent operator-controlled second copy;
- isolated restore.

Hetzner, VPS hosting, public DNS/TLS, Caddy and Backblaze B2 are not mandatory gates.

## M3 — External providers/accounting — ACTIVE, external evidence absent
Brevo, Stripe business-billing boundary and the Stripe → Webify accounting → VERIDRA ledger structure are selected/defined. No provider/accounting credit is granted until real sandbox/account/configuration and reconciliation evidence exists.

## Gate 3 — External beta/testing ready — FAIL
Requires the actual hardened Windows-local operator runtime, real SMTP flows required by the business workflow, local operational preflight/browser acceptance, verified recovery and no unresolved P0 affecting customer data/safety.

## Gate 4 — Real prospect ready — FAIL
Requires external-beta readiness **and** #297 real-SMB digital-presence validation, Stripe sandbox lifecycle, accounting/invoice exercise, usable/approved Priority-A paperwork, complete actual-provider dry run, no first-customer P0/P1 and Rafael's explicit #284 approval. **No real outreach permitted.**

## Gate 5 — Production ready — FAIL
Requires exact release/config/evidence freeze, secret management, verified backups/restore, observability, provider go-live decisions, runbook and human operator acceptance.

## Fully operative definition
100% means VERIDRA/Webify has proven all weighted gates above, including real-SMB digital-presence value, and at least one real paying customer completes activation and at least one recurring service/payment cycle successfully, with reconciliation, monitoring/reporting, measured operator economics and no unresolved P0/P1 operational gap.


### #297 completion update — 2026-09-25
- 25-business Ireland dental cohort completed with preserved acquisition failures.
- 11/11 evidence-sufficient businesses human reviewed.
- Human bounded-review median: 15 minutes across 7 usable timings.
- 8 human-confirmed material misses; 0 material qualification-changing false positives.
- Finding-level bounded sample stored in `.ai/PHASE_C_FINDING_VALIDATION_SAMPLE.json`: 33 sampled / 5 true / 1 false / 27 unverified. The 83.3%/16.7% adjudicated TP/FP rates apply only to the six adjudicated items and are not a full-cohort accuracy score.
- 4 no-contact shadow Presence Care deliveries completed.
- Customer report v6 master direction human accepted and documented in `.ai/CUSTOMER_REPORT_DESIGN_SYSTEM.md`.
- Recurring-value decision: **CONDITIONAL**. Presence Care is supported for qualified recurring-risk businesses, not as a universal €99/month offer.
- REAL OUTREACH COUNT remains 0.
- #297 is complete; #296 and #284 remain blockers before real outreach.


### 2026-09-25 architecture correction
#296 was corrected to the intended operator-local model. Cloud-hosting artifacts remain optional research and do not count as blockers or operability evidence. Weighted operability remains **49%** until the actual Windows-local runtime/recovery/provider gates are proven.


### 2026-09-26 M2 near-complete actual-workstation evidence
The canonical Windows workstation has now proven hardened loopback operation, durable state, process supervision, controlled restart, live/ready checks, hardened routes, verified backup, an integrity-matched copy on a separate physical disk, isolated restore, SQLite integrity, and restrictive ACLs on runtime/config/data. This earns **11/12 M2 points**. Only restart/persistence after an actual Windows or user-session reboot remains before full M2 closure. Weighted operability is therefore **60%**. No M3/M4/M5 credit is inferred.
