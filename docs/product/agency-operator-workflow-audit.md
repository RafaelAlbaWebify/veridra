# Agency operator workflow audit

## Purpose

This document reviews Veridra as an end-to-end commercial workflow for a non-technical agency operator. It is based on the current runtime composition and visible application entry points, not only on module existence.

Veridra's intended commercial loop is:

1. onboard an agency tenant;
2. configure the workspace and team;
3. create a client project;
4. choose a bounded crawl profile;
5. run and review an audit;
6. configure a white-label report profile;
7. generate and deliver a report;
8. capture and qualify leads;
9. convert findings into remediation tasks;
10. schedule monitoring;
11. rescan and prove improvements.

## Verified implementation inventory

The composed runtime registers authenticated identity, invitation, session, tenant project, history, report, lead, lead-form, task, monitoring, monitoring-job, report-profile and workspace APIs. It also registers operator-facing project, task, lead, PDF, crawl-profile, monitoring, commercial, workspace, member and assignment surfaces.

The current assessment dashboard exposes a website URL field, optional report-profile selection, assessment execution, report opening, evidence export and local save actions. It also links to client projects, reports, report profiles and history.

The product therefore has broad functional coverage. The principal commercial risk is no longer absence of modules; it is whether operators can discover the correct sequence, understand prerequisites and move from one completed action to the next without consulting implementation documentation.

## Journey assessment

### 1. Tenant and agency onboarding

**Implemented foundation**

- authenticated tenant identity and membership boundaries;
- owner bootstrap, password management and invitation flows;
- server-side request identity and tenant-qualified APIs.

**Workflow risk**

The runtime exposes the necessary identity operations, but the product documentation and primary navigation do not yet demonstrate a single guided agency setup path. A new operator can encounter workspace, members, projects and report profiles as separate concepts without a visible recommended order.

**Required refinement**

Provide a first-run checklist showing: create agency profile, invite team, add first client, choose crawl profile, run first audit and create first branded report.

### 2. Workspace setup and team permissions

**Implemented foundation**

- workspace plans, usage metering and entitlement enforcement;
- owner, administrator, analyst, sales and viewer roles;
- member assignment and append-only operator audit events.

**Workflow risk**

Entitlements and permissions are commercially important but can remain invisible until an action is rejected. Operators need to see their current plan, remaining usage and role capabilities before reaching a blocked action.

**Required refinement**

Add persistent workspace context to the operator shell: active plan, usage summary, current tenant and current role. Permission-denied responses should point to the relevant workspace or member-management page without disclosing cross-tenant information.

### 3. Client project creation and crawl profile selection

**Implemented foundation**

- tenant-qualified projects;
- validated crawl profiles and project-level crawl limits;
- bounded same-origin collection with sitemap discovery and page-level findings.

**Workflow risk**

The assessment dashboard begins with a one-off website assessment while persistent client work begins under Client projects. The distinction between a quick audit and a monitored client project is not sufficiently explicit in the primary navigation.

**Required refinement**

Present two clear entry points:

- **Quick audit** — temporary assessment with optional report/export;
- **Client project** — saved client, selected crawl profile, recurring history, tasks and monitoring.

After a quick audit, offer an explicit conversion action that creates a project using the audited target and selected report profile.

### 4. Audit execution and finding review

**Implemented foundation**

- multi-area findings with deterministic evidence;
- page-level duplicate metadata, missing-alt, redirect-chain and HTML-size findings;
- affected URLs and bounded crawl evidence;
- filtered finding views and priority actions.

**Workflow risk**

The current dashboard prioritises the first five attention findings in deterministic order, but it does not visibly explain the prioritisation model or connect each finding directly to project remediation work.

**Required refinement**

For project assessments, each actionable finding should expose:

- affected-page count and expandable affected URLs;
- business impact and implementation guidance;
- create-task action;
- existing task status when already linked;
- first seen, last seen and comparison status where history exists.

### 5. White-label report configuration and generation

**Implemented foundation**

- reusable report profiles;
- HTML, server-generated PDF and evidence ZIP outputs;
- organisation/client branding, selected sections and calls to action.

**Workflow risk**

Report-profile management and report generation are separate surfaces. The operator dashboard links to both Reports and Report profiles, but the visible journey does not make the prerequisite relationship clear.

**Required refinement**

Use a report wizard attached to the client project:

1. choose or create report profile;
2. select assessment;
3. preview included sections;
4. generate HTML/PDF;
5. choose delivery or copy-link action;
6. show delivery and engagement status.

### 6. Report delivery and lead capture

**Implemented foundation**

- outbound email delivery attempts;
- embeddable tenant-bound lead forms;
- webhook history;
- report-open and CTA engagement tracking;
- lead ownership, follow-up, retention and analytics.

**Workflow risk**

These capabilities can appear as independent administrative tools rather than one understandable sales loop. Agencies need a direct relationship between embedded form, captured lead, generated report, engagement event and next sales action.

**Required refinement**

The lead detail view should be the commercial hub showing:

- submitted website and contact details;
- generated assessment/report;
- delivery attempts;
- report-open and CTA events;
- owner, status and next follow-up;
- convert-to-project action;
- retention and deletion controls.

### 7. Remediation tasks

**Implemented foundation**

- tenant-qualified remediation tasks;
- supported workflow statuses, ownership, due date and source assessment references.

**Workflow risk**

Task creation must be discoverable from the finding itself. A separate task-management page is useful for operations but should not be the only entry point.

**Required refinement**

Create tasks from findings with the source finding, affected URLs, evidence and recommendation pre-populated. Preserve operator edits and link the task back to the current and source assessments.

### 8. Monitoring, rescan and proof of improvement

**Implemented foundation**

- project monitoring schedules;
- durable tenant monitoring jobs and bounded worker leases;
- project history and comparison;
- email-attempt persistence.

**Workflow risk**

The durable queue and worker model are operational foundations. Operators still need a simple product-level state: next scheduled run, last run, latest outcome, changes found and delivery status.

**Required refinement**

The project overview should show:

- monitoring enabled/disabled;
- next due run;
- latest job state;
- latest assessment outcome;
- added, resolved, changed and unchanged findings;
- task verification candidates;
- report/notification delivery result.

## Commercial-severity ranking

### Critical

1. No single guided operator journey from onboarding to first branded client report.
2. Quick audits and persistent client projects are not clearly separated or convertible.
3. Finding review does not yet present task creation and verification as the obvious next action.
4. Lead capture, report delivery, engagement tracking and project conversion are not yet presented as one sales workflow.

### High

5. Workspace plan, quota and role context are not persistently visible before actions are blocked.
6. Monitoring infrastructure is stronger than the visible project-level monitoring status and next-action UX.
7. Report configuration, generation and delivery require a clearer project-attached wizard.

### Medium

8. Current documentation still describes an obsolete 1.0 loopback-only product state.
9. Legacy and tenant-qualified concepts need clearer operator-facing terminology and retirement boundaries.
10. Production email configuration, supervised deployment and operational onboarding remain deployment prerequisites rather than completed hosted-SaaS capabilities.

## Recommended coherent next milestone

Implement an **agency workflow shell and project conversion path** before adding another audit detector.

The milestone should include:

1. a tenant-aware operator navigation shell with current workspace, role, plan and usage context;
2. explicit Quick audit and Client projects entry points;
3. conversion of a completed quick audit into a tenant-qualified project;
4. project overview actions for run audit, review findings, create report, create tasks and configure monitoring;
5. contextual next-step panels after project creation, assessment completion and report generation;
6. deterministic route, permission, tenant-isolation and Chromium workflow tests;
7. documentation that distinguishes locally verified functionality from production deployment readiness.

## Explicit nonclaims

This audit does not claim:

- that the complete hosted SaaS onboarding journey is production-ready;
- that email delivery is operational without a configured provider;
- that billing collection or subscription lifecycle management is complete;
- that automated accessibility findings establish WCAG conformance;
- that passive security findings are a penetration test;
- that AI readiness proves visibility in any model;
- that Veridra contains proprietary keyword, backlink, traffic or rank-tracking datasets.
