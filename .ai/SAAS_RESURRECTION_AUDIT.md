# VERIDRA SaaS resurrection audit

Status: active
Started: 2026-10-02

## Goal

Recover and productize the hosted/multi-tenant VERIDRA capability without weakening or replacing the supported `VERIDRA_ENV=operator` Webify workflow.

The target hosted product is the agency website-audit / white-label / lead-generation product defined at the end of VERIDRA 12. The operator product remains a separate supported runtime over the same core.

## Product split

- `VERIDRA_ENV=operator`
  - Webify internal/operator-local product.
  - Loopback-only.
  - No public signup, SaaS billing, inbound lead forms, or team surfaces.
  - Existing #279/#284/#296 work remains relevant to this track.

- `VERIDRA_ENV=production`
  - Hosted agency product.
  - Tenant-qualified identity and storage.
  - Signup/login, plan/usage, Stripe billing, teams, branded reporting, embedded lead forms, projects and recurring monitoring.
  - Requires a separate commercial-product roadmap and acceptance gate.

## Phase 0 classification

| Capability | Classification | Evidence / notes |
| --- | --- | --- |
| Runtime production boundary | KEEP | Explicit HTTPS trusted origin, allowed hosts, body limits, forwarded-header rejection policy and production config validation exist. Caddy deliberately strips forwarded identity headers before the app. |
| Signup | KEEP | Email verification, password creation, workspace creation, legal evidence, non-enumerating existing-email behaviour and failure cleanup exist. |
| Browser login / recovery | KEEP | Password login, throttling, server-side session issuance and password recovery exist. |
| Bootstrap onboarding | REMOVE FROM PRODUCTION | Local first-owner bootstrap is development/test only. Production route composition and login navigation no longer expose it. |
| Tenant/workspace isolation | KEEP / REVALIDATE HOSTED E2E | Tenant-qualified identity/stores are widespread. Lead source assessments were a discovered exception and new bound captures now persist under `tenants/<tenant>/lead-assessments/`; legacy read fallback is retained only for old data compatibility. |
| Plan catalogue / quotas | KEEP, REVISIT COMMERCIAL LIMITS | Free/Solo/Professional/Agency limits exist. Project, audit, crawled-page, PDF, export, monitoring, lead submission and seat enforcement are now covered through hosted paths; final commercial quantities/prices remain a business decision. |
| Usage reservations | KEEP | Explicit reserve / record-reserved / release lifecycle now prevents max-page reservations from leaking capacity when actual usage is lower or work fails. |
| Public pricing page | REWORK | Plans render capacity but paid public prices are intentionally not duplicated. New commercial positioning requires transparent public pricing after final price approval. |
| Stripe subscription flow | KEEP, REVALIDATE PROVIDER | Checkout, Portal, signature verification, idempotent checkout reservation, current-subscription retrieval, authoritative webhook projection and suspension/cancellation mapping exist. Real Stripe test-provider lifecycle is not yet proven. |
| Hosted agency navigation | KEEP/REWORK | Hosted and operator branding/IA are separated. Hosted prioritises audits/delivery, leads and workspace/billing; entitlement-aware lock/upgrade UX remains. |
| Hosted home/dashboard | KEEP/REWORK | Hosted `/agency` now prioritises audit, projects/reports, leads/forms, plan, billing and team rather than the Webify prospect workflow. Further commercial dashboard metrics/polish remain. |
| Quick audit -> project conversion | KEEP | Hosted quick audit requires identity, consumes audit/page usage and project conversion enforces capacity. Operator behavior remains separate. |
| Projects | KEEP | Tenant projects, crawl profiles, histories and capacity enforcement exist. Direct API capacity bypass was closed. |
| Multi-page crawl | KEEP/REWORK SCALE | Quick/standard/deep profiles currently support up to 10/25/100 pages. Larger commercial tiers require an asynchronous job/progress model before raising caps. |
| White-label report profiles | KEEP/REWORK UX | Organisation/client/contact/logo/accent/intro/summary/conclusion/CTA/language/section controls exist. Production create/select/edit/use now enforces white-label entitlement; downgrade hub remains recoverable through Default Veridra profile. |
| PDF / evidence exports | KEEP/REWORK POLISH | Playwright PDF, page numbers and evidence exports exist. Hosted PDF/export and SMTP report PDF now consume plan usage with reservation cleanup. TOC/charts/page-break/template polish remains. |
| Monitoring/comparison | KEEP | Manual and worker execution share one tenant-aware executor. Hosted production reserves/records monitoring runs and actual crawled pages; failures release reservations. New/resolved/persistent/page-change comparison already exists. |
| Remediation/tasks | KEEP | Full task lifecycle including accepted risk, verification required and verified evidence exists. |
| Embedded audit lead forms | KEEP/REWORK UX | Tenant-bound forms, consent, origins, notifications, webhook and CTA exist. Production management now enforces embedded-form entitlement; public capture requires tenant binding, meters audit/lead/pages and no longer falls back to global legacy storage. |
| Lead management | KEEP/REWORK UX | Lead status/owner/follow-up/value/won/lost/activity and project conversion exist. Lead conversion inherits project capacity. New bound source assessments are tenant durable; legacy source reads remain for compatibility. |
| Public abuse/rate limiting | REWORK / PRODUCTION HARDENING | Embedded forms have a process-local 5/hour limiter keyed by request peer. Behind the current Caddy boundary the peer may be shared, so rate-limit semantics need a proxy-aware design before public launch. Free public tools also need an explicit abuse-control policy. |
| Team/memberships | KEEP/REVALIDATE UX | Real tenant roles/memberships exist. Invitation acceptance rechecks plan seat capacity inside an immediate SQLite transaction before membership creation, preventing accepted-seat overcommit. Pending-invitation UX may still be improved. |
| Hosted deployment | KEEP AS SINGLE-HOST MVP | Compose/Caddy/web/worker/persistent volume and production hardening exist. SQLite + filesystem state requires one authoritative durable volume and quiesced cross-store backups; no horizontal/multi-node claim. |
| Backup/restore | KEEP / HOST VALIDATION NEEDED | Verified manifest/hash/integrity backup and controlled restore include identity, identity-email evidence, full tenant root and monitoring jobs. Real off-host restore/provider reconciliation still required. |
| Custom domain | MISSING / LATER | Not required for initial hosted release. |
| Report open / CTA click analytics | MISSING / LATER | No current implementation found; not initial-release critical. |

## Changes made during Phase 0

1. Separated `operator` and hosted product branding/runtime navigation.
2. Reoriented hosted home around audits, client delivery, inbound leads and workspace management.
3. Added hosted runtime route-inventory regression protection.
4. Removed development bootstrap onboarding from production composition/navigation.
5. Added explicit usage reservation reconciliation/release and closed leaked-capacity behavior.
6. Closed direct tenant-project API capacity bypass.
7. Routed hosted quick audits and conversion assessments through authenticated tenant metering.
8. Enforced production white-label entitlement across create/select/edit/output paths.
9. Metered hosted PDF, export and SMTP-delivery PDF generation.
10. Kept report hub recoverable after plan downgrade by allowing return to Default Veridra profile.
11. Centralized manual/worker monitoring execution and metered hosted monitoring + actual crawl pages.
12. Enforced embedded-lead-form entitlement in hosted management UI.
13. Removed production unbound/legacy fallback from embedded lead capture.
14. Added capture reservation cleanup and actual crawl-page accounting.
15. Confirmed lead-to-project conversion inherits project capacity enforcement.
16. Moved new bound lead source assessments into tenant durable storage and retained legacy read compatibility for historical leads.
17. Verified membership acceptance rechecks seat capacity transactionally.
18. Reviewed Stripe authority/webhook lifecycle; retained for provider acceptance rather than rewrite.
19. Promoted single-host deployment bundle to the hosted MVP architecture while keeping it separate from operator readiness.
20. Superseded internal-only product decision D-002 with dual-runtime D-012.
21. Reconciled README, strategy, AI context and roadmap; removed stale global VERIDRA readiness percentages.

## Remaining Phase 0 closeout / next implementation boundary

### Must close before H0 is complete

1. Keep repository CI green on the final integrated head.
2. Add/retain regression evidence for tenant-scoped lead source assessments and reservation cleanup.
3. Reconcile any remaining operator-only wording in durable hosted/deployment docs that materially affects future execution.
4. Record the public abuse/rate-limit problem as a hosted production blocker or implement a proxy-safe design.
5. Produce the final implementation roadmap from this matrix.

### After H0

Move to the hosted roadmap in `docs/product/strategy-and-roadmap.md`:

- H1 commercial integrity acceptance;
- H2 commercial UX;
- H3 report polish;
- H4 larger-crawl job model;
- H5 lead-generation polish;
- H6 real provider lifecycle;
- H7 hosted deployment/human acceptance.

Do not add Ahrefs/Semrush-scale data, active vulnerability scanning, custom domains or analytics merely for feature count.

## Acceptance rule

Implementation presence is not proof of operability. Each hosted capability must be tracked separately as:

- implemented;
- regression-tested;
- integrated in the production runtime;
- manually accepted in a realistic hosted flow;
- externally/provider-validated where applicable.
