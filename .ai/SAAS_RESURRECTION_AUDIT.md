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
| Runtime production boundary | KEEP | Explicit HTTPS trusted origin, allowed hosts, body limits, trusted proxy handling and production config validation exist. |
| Signup | KEEP | Email verification, password creation, workspace creation, optional legal evidence, non-enumerating existing-email behaviour and failure cleanup exist. |
| Browser login / recovery | KEEP | Password login, throttling, session issuance and password reset exist. |
| Bootstrap onboarding | REMOVE FROM PRODUCTION | Local first-owner bootstrap is a development/test tool, not SaaS signup. Production already rejected it at handler level; 2026-10-02 it was also removed from production composition and login navigation. |
| Tenant/workspace isolation | KEEP | Tenant-qualified stores and capability checks are widespread; dedicated isolation tests exist. |
| Plan catalogue / quotas | KEEP, REVISIT LIMITS | Free/Solo/Professional/Agency catalogue, project caps, audit/page/PDF/export/lead/monitoring quotas and seats exist. Commercial limits still need final modelling. |
| Public pricing page | REWORK | Catalogue is rendered but paid public prices are deliberately not shown. New positioning requires transparent pricing once final prices are approved. |
| Stripe subscription flow | KEEP, REVALIDATE PROVIDER | Checkout, portal, webhook verification, idempotent reservation and entitlement reconciliation exist. Requires live/test-provider acceptance for the hosted product. |
| Hosted agency navigation | REWORK | Hosted and operator surfaces shared copy. 2026-10-02 first split added: hosted shows Agency workspace and operator retains Webify operator branding. |
| Hosted home/dashboard | REWORK | Current `/agency` still centres the Webify prospect-discovery workflow. Hosted product should eventually prioritise audits, projects, leads, reports and monitoring. Do not rewrite until the remaining Phase 0 route audit is complete. |
| Quick audit -> project conversion | KEEP/REWORK | Hosted mode supports temporary audit and explicit tenant project conversion with crawl/profile selection. UX and entitlement behaviour need commercial review. |
| Projects | KEEP | Tenant projects, crawl profiles, assessments, histories and quota-aware project capacity exist. |
| White-label report profiles | KEEP | Organisation/client/contact, logo, accent colour, intro/summary/conclusion/CTA, language, section selection/order exist. |
| PDF reports | KEEP/REWORK | Safe Playwright A4 rendering, page numbers and branding exist. Commercial polish (TOC/charts/page breaks/templates) remains. |
| Monitoring/comparison | KEEP | Manual/daily/weekly/monthly schedules, worker/jobs and new/resolved/persistent/page-change comparison exist. |
| Remediation/tasks | KEEP | Full task lifecycle including accepted risk, verification required and verified evidence exists. |
| Embedded audit lead forms | KEEP/REWORK | Tenant-bound forms, consent, allowed origins, rate limiting, notification, webhook, CTA and audit capture exist. Product UX/embed setup still needs work. |
| Lead management | KEEP/REWORK | Lead status, owner, follow-up, value, won/lost, activity history and project conversion exist. |
| Team/memberships | KEEP/REVALIDATE | Tenant roles, membership management and seat entitlements exist. Hosted UX/security acceptance still required. |
| Custom domain | MISSING / LATER | No hosted custom-domain product surface found. Not needed for initial release. |
| Report open / CTA click analytics | MISSING / LATER | No evidence found in current code. Not release-critical unless chosen for parity. |

## Changes made during Phase 0

1. Separated navigation branding:
   - operator: `Webify operator`
   - hosted: `Agency workspace`
2. Separated hosted home intro/title from operator-only copy.
3. Added hosted-product route inventory regression coverage.
4. Removed bootstrap onboarding from production route composition.
5. Removed the dead `First-time setup` onboarding link from production login.
6. Added regression tests for hosted vs operator surfaces.

## Next audit slice

Continue in this order:

1. Hosted dashboard / information architecture.
2. Project creation and audit flow under plan quotas.
3. White-label profile/report/PDF end-to-end.
4. Monitoring jobs and usage accounting.
5. Lead form creation -> public capture -> lead management -> project conversion.
6. Team seats and invitation flow.
7. Stripe checkout/webhook/cancellation lifecycle.
8. Production deployment assumptions, storage model, concurrency and backup/restore.
9. Final KEEP / REWORK / MISSING / REMOVE matrix and implementation roadmap.

## Acceptance rule

Implementation presence is not proof of operability. Each hosted capability must be tracked separately as:

- implemented;
- regression-tested;
- integrated in the production runtime;
- manually accepted in a realistic hosted flow;
- externally/provider-validated where applicable.
