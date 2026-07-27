# Agency operator workflow audit

## Purpose

This document reviews Veridra as an end-to-end commercial workflow for a non-technical agency operator. It is based on the composed runtime and visible application entry points, not only on module existence.

## Intended commercial loop

1. onboard an agency tenant;
2. configure workspace and team;
3. run a quick audit or create a client project;
4. choose a bounded crawl profile;
5. review findings and affected URLs;
6. configure a white-label report;
7. deliver the report;
8. capture and qualify leads;
9. convert findings into remediation tasks;
10. schedule monitoring;
11. rescan and prove improvements.

## Verified implementation inventory

The runtime includes authenticated identity, tenant-qualified projects, history, reports, leads, lead forms, tasks, monitoring, monitoring jobs, report profiles, workspace plans, members and assignments. The merged agency workflow shell now provides explicit Quick audit and Client projects entry points.

The principal remaining commercial risk is not missing modules. It is continuity between those modules: operators must understand prerequisites, next actions and the difference between temporary and persistent work.

## Current workflow assessment

### Onboarding and workspace

Authentication, memberships, roles, invitations, password recovery and tenant boundaries exist. A complete first-run checklist and persistent visibility of tenant, role, plan and usage remain incomplete.

### Quick audits and client projects

The agency shell now clearly separates one-off audits from persistent projects. The next missing action is explicit conversion of a completed quick audit into a tenant-qualified project without accepting a client-controlled tenant identifier or persisting automatically.

### Finding review and remediation

Findings include deterministic evidence and affected URLs. Project findings should directly expose task creation, existing task state, first-seen/last-seen evidence and rescan verification status.

### Reporting

Reusable report profiles and HTML, PDF and evidence ZIP outputs exist. The project workflow still needs a guided report sequence: choose profile, select assessment, preview sections, generate, deliver and review delivery/engagement state.

### Leads and commercial operations

Lead forms, captured leads, report-open and CTA events, outbound delivery attempts, ownership, follow-up, retention and analytics exist. They should be presented as one sales workflow with a visible convert-to-project action.

### Monitoring

Schedules, durable tenant monitoring jobs, bounded worker leases, history and comparisons exist. Project pages still need a simple status view showing next run, latest job, latest assessment, changed findings, verification candidates and delivery outcome.

## Commercial-severity ranking

### Critical

1. No explicit quick-audit-to-project conversion.
2. Finding review does not yet make task creation and later verification the obvious path.
3. Lead capture, report delivery, engagement and project conversion remain fragmented.

### High

4. Workspace plan, quota, tenant and role context are not persistently visible.
5. Monitoring infrastructure is stronger than the project-level monitoring UX.
6. Report configuration, generation and delivery need a project-attached workflow.

### Medium

7. Legacy local and tenant-qualified concepts need clearer retirement boundaries.
8. Hosted email, billing and deployment operations remain environment-dependent rather than complete SaaS operations.

## Next coherent milestone

Implement quick-audit-to-project conversion:

- offer conversion only after a completed audit;
- preserve the normalized public target and selected report profile;
- require explicit project name/client confirmation;
- derive tenant identity exclusively from verified server-side identity;
- enforce project capacity and permissions before persistence;
- create no project on GET or audit execution alone;
- redirect to the created project overview;
- add route, permission, tenant-isolation and Chromium tests.

## Explicit nonclaims

This audit does not claim that hosted SaaS onboarding, payment collection, SMTP delivery or deployment orchestration are complete. Accessibility findings are not WCAG certification, passive security is not penetration testing, and AI readiness does not prove model visibility.
