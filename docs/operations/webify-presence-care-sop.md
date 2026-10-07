# WEBIFY — Presence Care operating SOP

Status: **OPERATOR-READY DRAFT — requires Rafael's operational review before #296 closure**

Purpose: define the supported Webify operating sequence for a real customer while VERIDRA remains a private operator-local application on Rafael's Windows PC.

This SOP does not authorize real outreach, legal approval, live charging, or tax treatment by itself. Those remain governed by #284/#296 and the permanent client-operations document register.

## 1. Activation boundary

A delivery project may begin only after the commercial work-start gate is open.

Required sequence:

1. Prospect evidence and qualification are complete.
2. Outreach/privacy eligibility is recorded where outreach applies.
3. Discovery and proposal/quote are completed.
4. The accepted proposal has durable external acceptance evidence.
5. Customer record contains accepted terms/agreement evidence.
6. Any required upfront payment has authoritative external invoice/payment evidence.
7. VERIDRA shows **Work may start**.
8. Onboarding confirms:
   - primary contact;
   - agreed service scope;
   - commercial terms;
   - access/domain/hosting requirements;
   - kickoff.
9. Create and link the delivery project.
10. Run the first saved assessment and retain it as baseline evidence.

If any required commercial, payment, access, or scope evidence is missing, do not begin implementation work.

## 2. Assessment and remediation

For each delivery project:

1. Run the bounded saved assessment.
2. Review findings and affected-page evidence.
3. Perform human QA before client-facing delivery.
4. Create remediation tasks only for agreed, actionable findings.
5. Assign owner/status/due date where applicable.
6. Record implementation notes and evidence.
7. If verification is required, run a later saved assessment and select it in the remediation task.
8. Mark a task Verified only when later evidence demonstrates the original finding is resolved.
9. If blocked, record the blocker explicitly.
10. If the requested work exceeds agreed scope, stop remediation and use the Change Request path.

## 3. Definition of an included minor fix

The included 30-minute allowance applies only to a **minor fix**.

A task is a minor fix only when all of the following are true:

- the expected hands-on implementation time is **30 minutes or less** for one operator;
- the change is bounded to the existing website/application configuration;
- it does not require a new page, new template, redesign, new feature, new integration, migration, or platform replacement;
- it does not require substantial copywriting, asset production, stakeholder discovery, or third-party procurement;
- it does not require unsupported privileged access or material provider/account changes;
- it is low-risk and has a clear rollback or reversal path;
- acceptance can be demonstrated with existing VERIDRA assessment/remediation evidence;
- the work is already inside the agreed Presence Care scope.

Examples that may qualify when low-risk and within 30 minutes:
- correcting one or a few existing title/meta-description fields;
- fixing a small number of missing alt attributes when the correct text is unambiguous;
- correcting a broken internal link;
- applying a small configuration change to an existing supported plugin/module;
- correcting a simple contact/detail inconsistency on an existing page.

The following are not minor fixes:
- new page builds;
- redesigns or layout rebuilds;
- custom development;
- new analytics/payment/CRM integrations;
- hosting/domain migrations;
- large-scale content editing;
- accessibility remediation requiring substantial structural work;
- security incident response;
- work that is likely to exceed 30 minutes once investigated;
- any task whose scope, risk, authorization, or rollback path is unclear.

If the operator cannot confidently classify the task before starting, treat it as **out of scope** and use a Change Request rather than consuming the included allowance.

## 4. Access and credential handling

VERIDRA stores operational references and evidence, not customer secrets.

Rules:

- never store passwords, recovery codes, MFA codes, API secrets, private keys, payment-card data, or equivalent credentials in VERIDRA notes, tasks, reports, issues, chat, or repository files;
- use an approved external credential-sharing/password-management channel when customer access is required;
- record only the minimum access reference needed to identify what was granted and for what purpose;
- use least privilege and the shortest practical access duration;
- confirm authorization before making production changes;
- revoke or return access when it is no longer required;
- record handoff/access-revocation evidence at closure.

If safe access cannot be established, mark the work blocked rather than asking the customer to send credentials through an unsafe channel.

## 5. Production-change boundary

Before a material customer-facing production change:

1. confirm the change is authorized and within agreed scope;
2. record the related remediation task or Change Request;
3. identify the rollback/reversal method;
4. preserve appropriate pre-change evidence;
5. where the change could materially affect customer state or VERIDRA operational state, create a verified VERIDRA backup before proceeding;
6. implement the change;
7. verify the expected outcome;
8. record evidence and any deviation;
9. if verification fails, roll back or place the task in Blocked/Verification required as appropriate.

Do not represent an unverified change as complete.

## 6. Delivery, report and acceptance

When remediation for the agreed sprint is complete:

1. confirm the remediation gate is clear;
2. generate/preview the branded report;
3. download the PDF when required;
4. record external delivery evidence;
5. request customer review using the approved external channel;
6. record changes requested when applicable;
7. complete included revisions or route out-of-scope work through Change Request;
8. record customer acceptance evidence;
9. complete backup/access/documentation handoff;
10. resolve final-balance evidence where required;
11. close the project with a completion summary.

Presence Care must not be configured as a new service before delivery has reached the final completion/handoff gate.

## 7. Presence Care activation

Presence Care begins only after the completed delivery boundary.

Required sequence:

1. Open the eligible completed client project.
2. Configure the recurring plan:
   - scope;
   - deliverables;
   - exclusions;
   - fee/currency;
   - billing cadence;
   - service/monitoring cadence;
   - response/escalation expectations;
   - effective date.
3. Mark the plan offered.
4. Record external customer acceptance/reference.
5. Record start date, next billing date and renewal behavior.
6. Activate the recurring service.
7. Confirm the service is shown as **Active**.

No recurring work should be treated as active before accepted-plan evidence exists.

## 8. Recurring Presence Care cycle

For each service cycle:

1. review monitoring/assessment evidence;
2. triage new, persistent and resolved findings;
3. determine whether any requested implementation is:
   - included minor fix;
   - normal monitoring/reporting work;
   - blocked;
   - out of scope and requires Change Request.
4. perform approved included work;
5. record completed recurring deliverables and evidence;
6. generate/send the agreed recurring summary/report through the approved external channel;
7. record authoritative invoice/payment references;
8. update next billing/renewal dates;
9. record the next action.

Never silently expand recurring scope because a customer request appears small.

## 9. Payment failure and suspension

Stripe/accounting/provider systems remain authoritative for real payment state.

If payment is failed or overdue:

1. record the authoritative external invoice/payment reference;
2. move the recurring service to the supported payment-blocked state;
3. stop treating normal recurring delivery as active;
4. use the approved failed-payment communication;
5. do not delete evidence or customer state;
6. when authoritative payment recovery is confirmed, record the paid state and resume service.

Do not infer payment from an email or verbal statement when an authoritative provider/accounting record is expected.

## 10. Support and escalation

Normal operator handling:

- operational question inside agreed scope → record/update the relevant customer/project/task;
- implementation task inside minor-fix boundary → follow the minor-fix workflow;
- blocked access/dependency → mark Blocked and state the required resolution;
- potential incident, data exposure, credential compromise, destructive change, or material availability/security risk → stop normal work and escalate before making further changes;
- legal/privacy/tax uncertainty → do not improvise; use the qualified adviser/accounting/legal boundary;
- scope/price/timeline expansion → Change Request.

## 11. Change Request boundary

Use a Change Request whenever the customer asks for work that changes agreed scope, price, deliverables, assumptions, exclusions, or timeline.

Record:

- requested change;
- requested-by reference;
- scope impact;
- price impact;
- timeline impact;
- decision/approval evidence.

Do not perform out-of-scope work before the required approval/evidence exists.

## 12. Cancellation and offboarding

For Presence Care cancellation:

1. record cancellation notice and requested effective date;
2. continue only the work allowed during the notice period;
3. complete any required final deliverable/report;
4. settle or record the authoritative billing boundary;
5. complete ownership/access handoff;
6. revoke/return customer access that Webify no longer requires;
7. record the effective cancellation and handoff evidence;
8. confirm VERIDRA shows the recurring service as **Cancelled**;
9. apply the approved retention/deletion rules to customer operational data;
10. retain only records required for contractual, accounting, security, dispute, suppression, or legal-retention purposes.

Tenant/account-level deletion, if ever required, follows the verified tenant-offboarding procedure and its mandatory pre-offboarding backup. It is not equivalent to ordinary Presence Care cancellation.

## 13. Local VERIDRA operations during customer work

The supported runtime remains operator-local:

- start/open through the canonical operator launcher;
- bind only to `127.0.0.1`;
- run operator preflight before real-world acceptance;
- use status/restart controls rather than launching ad hoc duplicate processes;
- keep durable state beneath the approved Windows-local root;
- use verified backup/recovery tooling;
- preserve the exact operated commit in acceptance evidence.

A VERIDRA application failure must not be worked around by direct database/store mutation during the #296 dry run.

## 14. Evidence required for #296 dry run

The real-world synthetic dry run must preserve non-secret evidence of:

- operated commit and workstation;
- operator preflight;
- prospect/customer/project lifecycle;
- accepted commercial terms/order-form boundary;
- provider/accounting references;
- saved baseline assessment;
- remediation and change-control decisions;
- report delivery;
- customer acceptance/handoff;
- recurring monitoring/report cycle;
- payment failure and recovery;
- cancellation/offboarding;
- verified backup;
- independent second copy;
- isolated recovery test.

The dry run is not complete until P0/P1 blockers are reviewed and Rafael explicitly approves the resulting operating workflow.
