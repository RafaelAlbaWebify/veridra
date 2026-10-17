# Webify — first-customer launch gates

Status: **OPERATOR DECISION WORKSHEET / NOT OUTREACH APPROVAL**
Updated: 2026-10-13
Sources of authority: [#284](https://github.com/RafaelAlbaWebify/veridra/issues/284), [#296](https://github.com/RafaelAlbaWebify/veridra/issues/296), `docs/operations/webify-presence-care-sop.md`, `docs/operations/m3-presence-care-stripe-sandbox.md`.

## Objective

Reach the first qualified Webify customer without rebuilding completed VERIDRA capabilities or mixing **first outreach**, **first charge**, and **client delivery** acceptance. All real prospect outreach remains prohibited until the explicit #284 approval.

## What is already evidenced (do not repeat without a regression or changed environment)

- Public-only Ireland dental validation: #297 complete; 25-site cohort, 11 human reviews, four no-contact shadow deliveries; Presence Care recurring value is conditional, not universally established.
- M2 hardened private Windows/loopback runtime and recovery: previously evidenced on actual workstation. Reconfirm the *operated commit* when deploying new changes.
- Stripe **Webify Presence Care**, not VERIDRA SaaS: 2026-09-30 real sandbox activation/recurring payment, failure/recovery, cancellation and sales-ledger reference reconciliation. Sandbox evidence is not live invoicing/tax approval.
- Synthetic full supported-UI commercial lifecycle is implemented. Do one fresh integrated *operator* acceptance on the release candidate rather than treating earlier synthetic CI as live acceptance.

## Gate A — first authorized outbound prospect contact

All items required *before* sending the first real message. Keep **REAL OUTREACH COUNT = 0** until each is evidenced and Rafael explicitly authorizes #284.

| Item | Current evidence | Release decision |
| --- | --- | --- |
| Target qualification and bounded findings | #297 completed; choose a specific validated, appropriate business | Pending prospect-specific review |
| Contact source, identity/recipient and suppression checks | Acquisition/prospecting contract requires provenance, objection/suppression and named-professional fail-closed policy | Pending prospect-specific compliance record |
| First-touch privacy notice, legal basis and compliant channel/message | #284 and acquisition contract; do not equate public business data with unrestricted permission to email | Pending documented review |
| Customer-facing offer and delivery capacity | SOP exists; define offered scope, fee, exclusions and response plan for first prospect | Pending operator sign-off |
| Priority-A legal/privacy materials adequate for outreach and contracting | #296 register identifies draft/not-production-approved MSA, order form and DPA | Qualified review and clean release set required |
| Actual-local-runtime integrated synthetic dry run | #296 requires provider references, report, recurring flow, backup/restore without database shortcuts | Pending release-candidate run |
| Rafael's explicit outreach approval | #284 is open | **NOT APPROVED — DO NOT CONTACT** |

Preparation allowed while this gate is closed: prioritize the previously reviewed cohort, redo bounded public observations where stale, draft accurate individual offers, and rehearse workflows with synthetic contacts. Do not send invitations/messages, schedule contact with real prospects, or create live subscriptions.

## Gate B — first real agreement / charge

Required before processing a customer's actual payment or treating a live subscription as active. These are **transaction-specific** and may be finalized when the customer's entity, location and supply are known; they do not require inventing a fictional tax result before outreach.

| Item | Acceptance evidence |
| --- | --- |
| Customer-specific signed/accepted clean terms and order form | Version, acceptance timestamp and external reference in supported workflow |
| Correct customer classification, supply and VAT/invoice treatment | Current facts reviewed by qualified accounting/tax authority |
| Accounting/invoice system of record | Named authoritative system and actual invoice reference; statutory posting must not be inferred from sandbox sheet rows |
| Stripe live-business readiness and agreed payment route | Provider/account verification and live-product configuration approved; no reuse of SaaS billing keys |
| Stripe → accounting → VERIDRA traceability | Real provider/payment reference, accounting invoice entry and bounded operational mirror |
| Scope-dependent access authorization | Only if hands-on remediation is contracted; public assessment/report/monitoring does not require client website credentials |

## Gate C — paid delivery and first recurring cycle

- Follow `docs/operations/webify-presence-care-sop.md`: baseline assessment, human evidence QA, scoped remediation or public-only delivery, report and explicit customer acceptance.
- Track support/minor-fix allowance and out-of-scope change requests rather than assuming any website work is included.
- Activate recurring service only after accepted-plan evidence, follow authoritative provider payment status, deliver periodic monitoring/report and prove the first recurring reconciliation.
- Preserve backup and recovery evidence, record operator time and economics, and only then claim actual first-customer operability.

## Smallest next operator exercise

1. Select **one existing reviewed Irish dental business** as a no-contact rehearsal target (no outbound messaging).
2. Refresh public findings and pick only high-confidence, business-understandable issues; flag stale/unverified claims.
3. Draft one commercial offer and one client-facing report based on actual evidence.
4. Run one synthetic reply → discovery → proposal → acceptance → Stripe sandbox/provider-reference → project/report → recurring → cancellation workflow through supported UI on the canonical Windows runtime.
5. Save non-secret screenshots/evidence, log specific blockers under #296 and request explicit human review of the offer, paperwork and actual contact eligibility under #284.

## Never infer

- A passing test or old Stripe SaaS run is not permission to send an email, charge a customer, or claim tax/legal approval.
- A spreadsheet row is not a statutory invoice or real bank settlement.
- No broad marketing automation, bulk contact or healthcare sensitive-data processing is authorized by this plan.
