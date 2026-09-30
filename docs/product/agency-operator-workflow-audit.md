# Operator-local application audit

## Purpose

This is the canonical product audit for the current VERIDRA architecture. The previous audit assumed a hosted multi-tenant agency SaaS; that assumption is retired for the supported Webify operator product.

## Canonical operator

- one Webify operator;
- local Windows runtime;
- loopback-only browser access;
- no normal login ceremony;
- no tenant/team/plan management in the operator journey;
- no customer login;
- external customer communication/payment/signature evidence is recorded rather than owned by VERIDRA.

## Supported workflow

1. Discover — find real businesses with bounded public evidence.
2. Qualify — score commercial fit.
3. Audit — persist prospect-specific public website evidence.
4. Outreach eligibility — validate market, mailbox type, source, role relevance, Privacy Notice readiness, suppression check and objections.
5. Conversation — only compliant/actually contacted prospects may progress.
6. Discovery/proposal — define measurable scope and proposal versions.
7. Acceptance/customer — accepted proposal evidence creates customer onboarding.
8. Work-start gate — accepted terms and required payment evidence before creating/linking delivery work.
9. Delivery — assessment, findings, remediation, report and monitoring.
10. Acceptance/handoff — unresolved work blocks review; acceptance evidence, handoff and closure are explicit.
11. Presence Care — recurring-service lifecycle mirrors authoritative provider evidence.

## Classification

### CORE

- operator home;
- prospect discovery/workbench/audit/compliance;
- deals/proposals/change requests;
- customers and work-start gate;
- client projects;
- project assessment/findings/tasks/reports;
- monitoring/progress;
- delivery/closure;
- recurring services.

### ADVANCED / SECONDARY

- manual prospect import;
- crawl-profile tuning;
- AI review JSON exchange;
- optional SMTP report sending;
- low-level tenant APIs used by supported agency workflows.

### LEGACY — EXCLUDED FROM OPERATOR

- public freemium landing;
- signup/login/onboarding;
- workspace/team/member UI;
- plan/quota enforcement;
- inbound lead forms/capture;
- SaaS Stripe plan billing;
- standalone crawl/report/export browser surfaces;
- hosted deployment journey.

## Findings from the 30 September 2026 re-audit

The re-audit was triggered because the technically passing application still exposed SaaS-era UX. Confirmed readiness defects included:

1. freemium landing on operator startup;
2. unnecessary login ceremony;
3. plan/team/workspace/inbound-lead navigation;
4. prospect discovery exposing implementation-level location/search controls;
5. dead commercial-dashboard link;
6. SaaS workspace quotas running in operator middleware;
7. standalone audit/report/crawl surfaces mounted beside the agency workflow;
8. SaaS Stripe billing/preflight in operator mode;
9. accepted-proposal strict route not guaranteeing Customer creation;
10. reply route bypassing outreach-compliance approval;
11. discovery/proposal routes bypassing compliance/conversation state;
12. duplicate transition routes making behavior depend on router registration order;
13. CI detecting a missing prospect audit helper and literal navigation placeholder.

## Corrections

The operator runtime now opens the agency workspace, auto-resolves the sole loopback owner, excludes SaaS-only surfaces, disables SaaS quota/billing enforcement, removes parallel standalone assessment surfaces, enforces outreach eligibility before reply/discovery/proposal progression, uses strict transition authorities, creates customer onboarding from accepted proposals and protects change incorporation behind approval plus a real proposal version.

## Remaining audit gate

No historical readiness percentage is authoritative after this re-audit.

Release requires:

1. CI green on the cleaned operator architecture;
2. one fresh Windows operator acceptance run after pulling these changes;
3. directed real-prospect discovery with no outreach, confirming usability and useful evidence;
4. reassessment of remaining legal/privacy publishing requirements;
5. only then a decision on reopening real outreach.

## Explicit nonclaims

- accessibility findings are heuristics, not WCAG certification;
- passive security is not penetration testing;
- AI technical readiness does not prove AI visibility;
- synthetic provider/customer evidence does not prove a real customer transaction;
- a technically passing happy path does not by itself establish operator usability.
