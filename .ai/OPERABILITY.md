# Operability Gates

## Current computed state
- Development usable: **PASS**
- Internal testing ready: **PASS**
- External beta/testing ready: **FAIL**
- Real prospect ready: **FAIL**
- Production ready: **FAIL**
- Weighted real-world operability: **42%**
- Remaining to full operability: **58%**
- M1 business readiness: **~95%**
- Real-SMB digital presence validation: **ACTIVE / 3 of 10 weighted points earned**
- M2 deployment tooling: **IMPLEMENTED / PARTLY TESTED IN CI / NOT DEPLOYED**
- REAL OUTREACH COUNT: **0**

Operability history:
- 33% → 36%: recurring/reporting/exception operating controls completed.
- 36% → 37%: Access Authorization and SOW/Change Order business-reconciled.
- 37% → 38%: Ireland first-market tax/invoice operating reference completed.
- 38% → 39%: EU/EEA transfer decisioning and Ireland-first dental/healthcare data/content operating boundaries completed.
- 39% → 40%: first no-contact real-SMB Ireland dental cohort actually run through VERIDRA; 20/25 full assessments succeeded and 5 target-acquisition failures were preserved as real-world evidence. Only 1/10 SMB-validation points credited because precision/value calibration remained incomplete.
- 40% → 41%: calibrated rerun of the exact frozen 25-site cohort improved full-assessment success from 20/25 (80%) to 22/25 (88%), converted all remaining acquisition failures into structured target-observation evidence, reduced high-severity insecure-resource prevalence from 9 sites to 3 while preserving genuine-looking active HTTP subresources, improved strict frozen-seed exact recall from 0/5 to 1/5 through the MB Dental explicit-update-age hit, and correctly kept the G-Dental copyright-only control unpromoted. Three material seed misses remained, mainly due bounded-crawl page selection.
- 41% → 42%: post-#300 frozen-cohort rerun on 2026-09-06 produced 21/25 full assessments with 4 structured target-observation failures and improved strict positive frozen-seed recall from the prior 1/5 (20%) to 2/4 evaluable (50%). Dublin City Dentist's public WordPress Sample Page is now detected and MB Dental remains correctly detected; the G-Dental copyright-only negative control remains 1/1 (100%). Dublin's phone placeholder and Crown Dental's hours contradiction remain evaluable misses, while Village Dental's two observations remain TLS-blocked.

Repository implementation, CI and architecture work do **not** automatically increase real-world operability. DEPLOYED / EXTERNALLY VERIFIED / PRODUCTION APPROVED / REAL-CUSTOMER PROVEN states require separate evidence.

## Weighted path to 100%
The weighting explicitly reserves real-world credit for proving SMB digital-presence value. Infrastructure/provider completion alone can never reach 100%.

- A Product engineering + synthetic lifecycle: **20%** — current 20/20.
- B M1 business operating layer: **20%** — current ~19/20 (~95%).
- C Real-SMB digital presence validation: **10%** — current 3/10.
- D M2 production infrastructure: **12%** — current 0/12 real-world credit.
- E M3 external providers/accounting: **8%** — current 0/8.
- F M4 production validation: **8%** — current 0/8.
- G M5 integrated actual-provider dry run: **8%** — current 0/8.
- H M6 human operator acceptance: **4%** — current 0/4.
- I First controlled prospect + paid activation: **5%** — current 0/5.
- J First recurring customer cycle: **4%** — current 0/4.
- K Closure/economics/no unresolved P0/P1: **1%** — current 0/1.

Total current weighted operability: **42/100**.

## Gate 1 — Development usable — PASS
Repository/package/application entrypoints exist and the current verified code baseline is green.

## Gate 2 — Internal testing ready — PASS
Latest fully verified repository evidence before the 2026-09-06 launcher-only follow-up: commit `01c1c6bd3918f15fade5d1ebacc5855afa9be755`, GitHub Actions run `34001492254`, success across Terraform validation, Linux Ruff/mypy/pytest/audit/browser/discovery/commercial acceptance and Windows portability/sales-contract/operator Playwright. The later Windows audit-archive selection fix is tracked separately until its CI run completes.

## M1 — Business-ready operating layer — ACTIVE (~95%)
Operating scope, activation/recurring SOP, payment/access/change/reporting/support/offboarding, Ireland tax/invoice, EU/EEA transfer decisioning and dental/healthcare data/content boundaries are defined. Remaining blockers are qualified production approval where required, actual transaction tax treatment, exact production-provider/entity/location evidence and clean approved customer-facing release set.

## C — Real-SMB digital presence validation — ACTIVE (#297)
Purpose: prove that VERIDRA + Webify Presence Care creates credible, understandable, remediable and recurring value for real SMBs rather than only passing synthetic website tests.

Initial market: Ireland.
Initial vertical: independent dental practices.

### Real evidence now earned
First real batch on 2026-09-05:
- 25 no-contact public dental websites targeted;
- 20 full assessments succeeded;
- 5 target acquisitions failed: 3 DNS resolution failures and 2 TLS certificate-verification failures caused by self-signed certificates;
- 588 attention findings emitted across the 20 successful assessments;
- median 28 attention findings per successful site.

Calibrated rerun on the same frozen cohort on 2026-09-05:
- 22/25 full assessments succeeded (88%);
- 3 failures remained, all classified as target observations;
- 642 attention findings across 22 successful assessments, median 28/site;
- strict exact manual-seed matches improved from 0/5 to 1/5 through `content.explicit-update-age` on MB Dental;
- G-Dental's 2024 copyright-only control remained intentionally unpromoted;
- high-severity active insecure-resource findings fell from 9 sites to 3.

Post-#300 frozen-cohort rerun on 2026-09-06:
- 21/25 full assessments succeeded;
- 4 structured target-observation failures: Village Dental TLS self-signed certificate, Lucan Dental DNS resolution, Shandon Dental DNS resolution, and Bandon Dental Care TLS self-signed certificate;
- frozen comparator positive_evaluable=4, positive_hits=2, strict_positive_recall=0.50;
- Dublin City Dentist Sample Page now matches `content.placeholder-default`;
- MB Dental remains a correct `content.explicit-update-age` hit;
- G-Dental negative control remains correct at 1/1 (100%);
- Dublin City Dentist's literal phone placeholder and Crown Dental's opening-hours contradiction remain evaluable misses;
- Village Dental's stale-content and hours-conflict observations remain unevaluable because strict TLS verification correctly blocks content acquisition.

This earns **3/10 C credit**. The third point is for measured real-world recall improvement with preserved negative-control behavior, not for code volume or finding count.

### Remaining calibration problems
The remaining evaluable material misses are:
- Dublin City Dentist literal `call phone number` placeholder copy;
- Crown Dental Dublin cross-page opening-hours contradiction.

Village Dental remains content-unavailable under strict TLS verification; VERIDRA must not bypass certificate validation merely to improve recall.

Required next sequence:
1. diagnose why Dublin phone placeholder is still missed despite owner-facing page selection;
2. diagnose why Crown's hours contradiction is still missed even after owner-facing crawl prioritization;
3. fix those analyzers/selection semantics without widening safety bounds indiscriminately;
4. rerun only as needed to verify the two remaining material misses and preserve the G-Dental negative control;
5. expand manual validation to the required 10–15 representative businesses and compute true-positive/false-positive/material-miss/commercial-value/operator-time metrics;
6. only after calibration quality is acceptable, run 3–5 no-contact shadow Presence Care deliveries.

Hard rule: sampled businesses are **not outreach targets during this track**. Do not contact them, submit forms, authenticate, modify systems or cross VERIDRA's bounded-public assessment boundary.

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
