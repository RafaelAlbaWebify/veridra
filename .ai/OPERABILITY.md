# Operability Gates

## Current computed state
- Development usable: **PASS**
- Internal testing ready: **PASS**
- External beta/testing ready: **FAIL**
- Real prospect ready: **FAIL**
- Production ready: **FAIL**
- Weighted real-world operability: **41%**
- Remaining to full operability: **59%**
- M1 business readiness: **~95%**
- Real-SMB digital presence validation: **ACTIVE / 2 of 10 weighted points earned**
- M2 deployment tooling: **IMPLEMENTED / PARTLY TESTED IN CI / NOT DEPLOYED**
- REAL OUTREACH COUNT: **0**

Operability history:
- 33% → 36%: recurring/reporting/exception operating controls completed.
- 36% → 37%: Access Authorization and SOW/Change Order business-reconciled.
- 37% → 38%: Ireland first-market tax/invoice operating reference completed.
- 38% → 39%: EU/EEA transfer decisioning and Ireland-first dental/healthcare data/content operating boundaries completed.
- 39% → 40%: first no-contact real-SMB Ireland dental cohort actually run through VERIDRA; 20/25 full assessments succeeded and 5 target-acquisition failures were preserved as real-world evidence. Only 1/10 SMB-validation points credited because precision/value calibration remained incomplete.
- 40% → 41%: calibrated rerun of the exact frozen 25-site cohort improved full-assessment success from 20/25 (80%) to 22/25 (88%), converted all remaining acquisition failures into structured target-observation evidence, reduced high-severity insecure-resource prevalence from 9 sites to 3 while preserving genuine-looking active HTTP subresources, improved strict frozen-seed exact recall from 0/5 to 1/5 through the MB Dental explicit-update-age hit, and correctly kept the G-Dental copyright-only control unpromoted. Three material seed misses remain, mainly due bounded-crawl page selection.

Repository implementation, CI and architecture work do **not** automatically increase real-world operability. DEPLOYED / EXTERNALLY VERIFIED / PRODUCTION APPROVED / REAL-CUSTOMER PROVEN states require separate evidence.

## Weighted path to 100%
The weighting explicitly reserves real-world credit for proving SMB digital-presence value. Infrastructure/provider completion alone can never reach 100%.

- A Product engineering + synthetic lifecycle: **20%** — current 20/20.
- B M1 business operating layer: **20%** — current ~19/20 (~95%).
- C Real-SMB digital presence validation: **10%** — current 2/10.
- D M2 production infrastructure: **12%** — current 0/12 real-world credit.
- E M3 external providers/accounting: **8%** — current 0/8.
- F M4 production validation: **8%** — current 0/8.
- G M5 integrated actual-provider dry run: **8%** — current 0/8.
- H M6 human operator acceptance: **4%** — current 0/4.
- I First controlled prospect + paid activation: **5%** — current 0/5.
- J First recurring customer cycle: **4%** — current 0/4.
- K Closure/economics/no unresolved P0/P1: **1%** — current 0/1.

Total current weighted operability: **41/100**.

## Gate 1 — Development usable — PASS
Repository/package/application entrypoints exist and the current verified code baseline is green.

## Gate 2 — Internal testing ready — PASS
Latest fully verified calibration code evidence: commit `0089f20ce5c6a6b929be856fce797ecc36289ed7`, GitHub Actions run `33950566526`, success across Terraform validation, Linux Ruff/mypy/pytest/audit/browser/discovery/commercial acceptance and Windows portability/sales-contract/operator Playwright.

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
- median 28 attention findings per successful site;
- durable summary: `evidence/smb-validation/ie-dental-batch-20260905-summary.json`;
- frozen manual-seed comparison: `evidence/smb-validation/ie-dental-manual-seed-comparison-20260905.csv`.

Calibrated rerun on the same frozen cohort:
- 22/25 full assessments succeeded (88%);
- 3 failures remain: 1 DNS resolution + 2 TLS certificate failures, all classified as `target_observation` rather than internal VERIDRA failure;
- Ardfallen Dental Practice and Shandon Dental moved from DNS acquisition failure to successful assessment;
- 642 attention findings across 22 successful assessments, median still 28/site;
- strict exact manual-seed matches improved from 0/5 to 1/5 through `content.explicit-update-age` on MB Dental;
- G-Dental's 2024 copyright-only control remained intentionally unpromoted;
- high-severity active insecure-resource findings fell from 9 sites to 3, with remaining evidence showing HTTP images/stylesheets rather than ordinary HTTP anchors/metadata;
- durable rerun summary: `evidence/smb-validation/ie-dental-rerun-20260905-summary.json`;
- rerun manual comparison: `evidence/smb-validation/ie-dental-manual-seed-comparison-rerun-20260905.csv`.

This earns **2/10 C credit**. The second point is for externally observed calibration improvement, not for code volume or finding count.

### Remaining calibration problems
The frozen seed contains 7 observations. Five are on currently successful sites; two Village Dental observations remain content-unavailable because strict TLS verification blocks the site.

Among the five evaluable observations, exact dedicated matches are **1/5**. The remaining material misses are:
- Dublin City Dentist public WordPress Sample Page;
- Dublin City Dentist literal `call phone number` placeholder copy;
- Crown Dental Dublin cross-page opening-hours contradiction.

The strongest newly isolated root cause is bounded crawl prioritization (#300). The 10-page budget can be consumed by low-value sitemap/article/media URLs before owner-facing pages such as contact/opening-hours/sample-page routes are assessed. The content analyzers cannot detect defects on pages they never receive.

Required next sequence:
1. fix #300 bounded-crawl selection without simply increasing limits;
2. prioritize homepage/contact/about/location/opening-hours/services/pricing and other owner-facing routes while preventing media assets from consuming HTML page budget;
3. rerun the exact frozen cohort and remeasure the three remaining material seed misses;
4. expand to the required 10–15 human validations and compute true-positive/false-positive/material-miss/commercial-value/operator-time metrics;
5. only then run 3–5 no-contact shadow Presence Care deliveries.

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
