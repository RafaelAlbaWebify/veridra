# Operability Gates

## Current computed state
- Development usable: **PASS**
- Internal testing ready: **PASS**
- External beta/testing ready: **FAIL**
- Real prospect ready: **FAIL**
- Production ready: **FAIL**
- Weighted real-world operability: **44%**
- Remaining to full operability: **56%**
- M1 business readiness: **~95%**
- Real-SMB digital presence validation: **ACTIVE / 5 of 10 weighted points earned**
- M2 deployment tooling: **IMPLEMENTED / PARTLY TESTED IN CI / NOT DEPLOYED**
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
- C Real-SMB digital presence validation: **10%** — current 5/10.
- D M2 production infrastructure: **12%** — current 0/12 real-world credit.
- E M3 external providers/accounting: **8%** — current 0/8.
- F M4 production validation: **8%** — current 0/8.
- G M5 integrated actual-provider dry run: **8%** — current 0/8.
- H M6 human operator acceptance: **4%** — current 0/4.
- I First controlled prospect + paid activation: **5%** — current 0/5.
- J First recurring customer cycle: **4%** — current 0/4.
- K Closure/economics/no unresolved P0/P1: **1%** — current 0/1.

Total current weighted operability: **44/100**.

## Gate 1 — Development usable — PASS
Repository/package/application entrypoints exist and the current verified code baseline is green.

## Gate 2 — Internal testing ready — PASS
Latest fully verified repository evidence: commit `897919d719af6fa86beec27419756c053449d991`, GitHub Actions run `34002932809`, success across Terraform validation, Linux Ruff/mypy/pytest/audit/browser/discovery/commercial acceptance and Windows portability/sales-contract/operator Playwright. This baseline includes the same-page multi-schedule opening-hours regression fix.

## M1 — Business-ready operating layer — ACTIVE (~95%)
Operating scope, activation/recurring SOP, payment/access/change/reporting/support/offboarding, Ireland tax/invoice, EU/EEA transfer decisioning and dental/healthcare data/content boundaries are defined. Remaining blockers are qualified production approval where required, actual transaction tax treatment, exact production-provider/entity/location evidence and clean approved customer-facing release set.

## C — Real-SMB digital presence validation — ACTIVE (#297)
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

Corrected Phase C rerun on 2026-09-23 (SMB Real Validation #11 / run `35885182337`):
- 22/25 full assessments succeeded and the same 3 acquisition failures remained;
- current adjudicated positive recall stayed 3/3 (100%) and negative control stayed 100%;
- Phase C review pack reduced from 263 attention findings / 48 families to **242 / 41** after evidence-driven acquisition, deduplication, local-presence, About-section and email-domain corrections;
- South Dublin Dental is again evaluable using 10 real HTML pages rather than the prior HTTP-202/169-byte representation;
- a deliberately conservative 67-finding high-confidence slice still gives **12/12** sampled businesses at least four credible remediation/value opportunities;
- this supports the existence of owner-facing value without depending on disputed/noisy families, but does **not** complete Phase C because full truth/commercial adjudication, material-human-miss evidence and operator-time evidence remain outstanding.

This still earns **5/10 C credit**; no additional operability credit is granted yet.

### Remaining #297 validation sequence
1. expand manual validation to 10–15 representative businesses and compute true-positive/false-positive/material-miss/owner-understandable/commercial-value/Webify-remediable/operator-time metrics;
2. run 3–5 no-contact shadow Presence Care deliveries;
3. measure activation work, monthly-allowance fit, separately quoted work and plausible recurring-cycle value;
4. make an explicit evidence-backed recurring-value decision for the Ireland €99/month model.

Hard rule: sampled businesses are **not outreach targets during this track**. Do not contact them, submit forms, authenticate, modify systems or bypass TLS validation.

## M2 — Production infrastructure — ACTIVE, external evidence absent
Implemented/tested repository evidence includes provider-neutral single-host deployment, Hetzner Terraform, Caddy TLS boundary, worker supervision, quiesced local backup and encrypted Backblaze B2 replication.

No M2 real-world credit is granted until evidence proves a real host, provider firewall, DNS/TLS, durable state, worker execution, real scheduled backup, independent off-host snapshot and isolated restore.

## M3 — External providers/accounting — ACTIVE, external evidence absent
Brevo, Stripe business-billing boundary and the Stripe → Webify accounting → VERIDRA ledger structure are selected/defined. No provider/accounting credit is granted until real sandbox/account/configuration and reconciliation evidence exists.

## Gate 3 — External beta/testing ready — FAIL
Requires real deployed infrastructure, real SMTP/public-origin identity-email flows, production preflight/deployment checks, operational health/logging and no unresolved P0 affecting tester data/safety.

## Gate 4 — Real prospect ready — FAIL
Requires external-beta readiness **and** #297 real-SMB digital-presence validation, Stripe sandbox lifecycle, accounting/invoice exercise, usable/approved Priority-A paperwork, complete actual-provider dry run, no first-customer P0/P1 and Rafael's explicit #284 approval. **No real outreach permitted.**

## Gate 5 — Production ready — FAIL
Requires exact release/config/evidence freeze, secret management, verified backups/restore, observability, provider go-live decisions, runbook and human operator acceptance.

## Fully operative definition
100% means VERIDRA/Webify has proven all weighted gates above, including real-SMB digital-presence value, and at least one real paying customer completes activation and at least one recurring service/payment cycle successfully, with reconciliation, monitoring/reporting, measured operator economics and no unresolved P0/P1 operational gap.
