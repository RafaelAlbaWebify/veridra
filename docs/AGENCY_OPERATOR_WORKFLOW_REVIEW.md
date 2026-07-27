# Agency operator workflow review

Reviewed against main `e2c3b710b1e3eb19e14a1032c3cc3cd317fbe0e1` after the tenant workspace-policy migration.

## Product position

Veridra is a white-label website-audit, lead-generation, remediation and monitoring product for agencies, freelancers and website-service businesses.

The implemented product loop follows the market-tested pattern:

```text
agency setup
  -> quick audit or embedded lead capture
  -> persistent client project
  -> saved multi-page assessment
  -> branded HTML/PDF/evidence report
  -> explicit report delivery
  -> remediation tasks
  -> scheduled or manual monitoring
  -> assessment comparison
```

Veridra adds bounded AI-readiness, trust, accessibility, public email-domain posture and passive public-security evidence. It does not claim penetration testing, a proprietary keyword or backlink index, universal AI visibility, traffic estimation or full Semrush/Ahrefs parity.

## Operator journey map

### 1. Tenant and workspace setup

- Administrative bootstrap: `veridra-identity-bootstrap`.
- Authentication: `/auth/login` and the existing session/password-recovery routes.
- Agency entry point: `/agency`.
- Workspace plan, entitlements, usage and plan history: `/workspace`.
- Team and role administration: `/workspace/members` and authenticated invitation/session APIs.

Result: the first tenant starts with a persisted Free workspace. Plan changes require the tenant-management capability and are recorded with actor, previous plan, new plan and timestamp.

Known gap: customer-facing first-tenant onboarding remains a CLI/bootstrap operation. Follow-up issue #123 owns the browser onboarding workflow.

### 2. Temporary quick audit

- Entry: `/agency/quick-audit`.
- Assessment console/result: `/` through the composed request-aware assessment router.
- API result: `/api/assess`.

A quick audit is temporary unless the operator explicitly confirms project conversion. Configured authenticated tenants reserve audit and crawl-page allowance before collection and record actual successful usage afterward.

### 3. Client project creation

- Explicit quick-audit conversion confirmation under `/agency/audits/...`.
- Canonical tenant conversion API under `/api/tenant/assessments/...`.
- Existing project surfaces under tenant project APIs and the agency project pages.

Project identity remains stable across report-profile, monitoring and other mutable configuration changes. Assessment history, tasks and monitoring references remain attached to the same project ID.

### 4. Multi-page assessment and findings

The assessment service performs bounded, sequential, same-origin collection with:

- validated crawl profiles and hard server limits;
- robots and sitemap discovery;
- sitemap-index and URL-set parsing;
- page/depth/byte/timeout limits;
- title, description, H1, canonical, status and mixed-content checks;
- broken internal-link evidence with source URLs;
- duplicate titles and descriptions;
- missing image-alt attributes;
- redirect-chain evidence;
- decoded HTML-size evidence;
- static accessibility checks;
- passive public-security checks;
- AI crawler and deterministic readiness signals;
- DNS and email-domain posture.

Affected URLs and common crawl metadata flow into saved findings, reports, evidence exports, comparisons and task conversion.

### 5. Finding review and remediation

- Project-attached saved findings: `/agency/projects/{project_id}/findings`.
- Explicit task confirmation: project/assessment/finding-specific agency route.
- Canonical task API: `/api/tenant/tasks` and finding-to-task conversion API.
- Task operations: agency task pages and tenant task APIs.

Task creation uses saved finding identity and server-side evidence. It is idempotent and does not claim that task creation or status alone proves remediation.

### 6. White-label report configuration

- Project report hub: `/agency/projects/{project_id}/reports`.
- In-context report-profile configuration: `/agency/projects/{project_id}/reports/profile`.
- Tenant report profile APIs under `/api/tenant/report-profiles`.

Profiles can control organisation/client identity, consultant and contact data, language, accent colour, introduction, conclusion, CTA, selected sections, ordering, raw-evidence visibility and bounded embedded logos. Project identity is preserved when the profile changes.

### 7. Report generation and delivery

From the project report hub the operator can:

- preview tenant-derived HTML;
- generate a bounded Chromium PDF;
- download the evidence ZIP;
- explicitly send the generated PDF by email;
- inspect immutable delivery attempts and retry as a new attempt.

Delivery records SMTP acceptance/failure/not-configured states. It does not claim inbox placement, report opening or CTA engagement unless separate bounded engagement evidence exists.

### 8. Embedded lead generation and lead management

- Tenant lead-form configuration APIs and durable form-to-tenant binding.
- Public form: `/embed/audit/{form_id}`.
- Agency lead inbox: `/agency/leads`.
- Lead detail/status/notes/export and bounded webhook/email delivery operations through existing tenant/commercial routes.
- Explicit lead-to-project confirmation under `/agency/leads/{lead_id}/convert`.

Public tenant identity comes only from the server-side binding. Successful bound submissions record audit and lead-submission usage for that tenant. Conversion preserves the source assessment and selected report profile and creates a durable lead-project link.

### 9. Monitoring and comparison

- Project monitoring: `/agency/projects/{project_id}/monitoring`.
- Tenant monitoring APIs and durable monitoring-job APIs.
- Bounded worker: `veridra-monitoring-worker`.
- Project comparison: `/agency/projects/{project_id}/compare`.

Operators can configure manual/daily/weekly/monthly monitoring, run explicitly, inspect saved assessment state and compare the latest assessment with the immediately previous one. Comparison labels added, resolved, changed and unchanged finding identifiers without treating identifier disappearance as automatic proof of remediation.

### 10. Entitlements, usage and audit evidence

Tenant-qualified workspace policy now covers:

- project capacity;
- report-profile and embedded-form features;
- audit and crawled-page usage;
- monitoring runs;
- PDF and evidence exports;
- lead submissions;
- direct project conversion.

Ambiguous legacy process-global workspace and usage files are ignored and never automatically assigned to a tenant. Remaining global helpers are standalone-compatibility quarantine only and are not imported by supported production modules.

## Route and surface classification

### Agency-primary browser surfaces

- `/agency`
- `/agency/quick-audit`
- `/agency/leads`
- `/agency/leads/{lead_id}/convert`
- `/agency/projects/{project_id}`
- `/agency/projects/{project_id}/findings`
- `/agency/projects/{project_id}/reports`
- `/agency/projects/{project_id}/reports/profile`
- `/agency/projects/{project_id}/monitoring`
- `/agency/projects/{project_id}/compare`
- project/finding/task confirmation pages beneath the agency namespace

### Tenant-qualified administration surfaces

- `/workspace`
- `/workspace/usage.csv`
- `/workspace/members`
- authenticated invitation, session and password-management routes

### Tenant APIs

- `/api/tenant/projects`
- `/api/tenant/history`
- `/api/tenant/reports`
- `/api/tenant/report-profiles`
- `/api/tenant/leads`
- `/api/tenant/lead-forms`
- `/api/tenant/tasks`
- `/api/tenant/monitoring`
- `/api/tenant/monitoring-jobs`
- conversion and finding-to-task APIs beneath `/api/tenant`

### Public surfaces

- `/embed/audit/{form_id}`
- explicitly public/free tools
- non-disclosing `/health` and `/ready`

### Standalone compatibility surfaces

- `veridra.app` and its local dashboard/history/project/profile routes;
- legacy local project, lead, task, commercial and monitoring pages retained for compatibility;
- quarantined process-global workspace helpers.

These compatibility surfaces are not the authoritative authenticated agency journey. Follow-up issue #124 owns navigation consolidation and composed-runtime retirement/concealment decisions.

## Commercial-severity review

### Critical: none inside the authenticated audit-to-monitoring loop

No remaining verified gap prevents an already bootstrapped tenant from performing the complete agency workflow.

### High: browser onboarding

A new customer still depends on administrative CLI bootstrap before using the browser product. This blocks self-service acquisition and is tracked in #123.

### High: duplicate navigation and compatibility surfaces

The composed runtime still contains overlapping legacy and agency routes. The authoritative journey exists, but navigation can expose technically similar destinations with different persistence and identity boundaries. This is tracked in #124.

### Medium: hosted commercial operations

Production boundaries are implemented and fail closed, but Veridra does not include provider-specific deployment, managed secrets, selected production SMTP, payment checkout, tax/invoice handling or external subscription truth. Local plan selection is entitlement policy, not proof of payment.

### Medium: external first-party integrations

Search Console, GA4, PageSpeed Insights/CrUX and Bing Webmaster Tools remain future provider-neutral enrichment. Current assessments use public evidence collected by Veridra and do not claim private first-party analytics.

### Deferred by strategy

- proprietary keyword/backlink databases;
- competitor traffic estimation;
- global rank-tracking infrastructure;
- active vulnerability scanning;
- universal AI-visibility scoring;
- custom-domain report hosting;
- enterprise SSO/MFA/federation;
- multi-region/distributed queue infrastructure.

## Capability status

### Implemented and exact-head CI verified

- bounded multi-page crawl and page-level evidence;
- saved tenant projects and assessment history;
- white-label HTML/PDF/evidence reports;
- project-attached report profile workflow;
- explicit report email delivery and attempt history;
- embedded tenant-bound audit forms;
- lead inbox and lead-to-project conversion;
- finding-to-task conversion and task operations;
- project monitoring and durable bounded worker;
- latest-versus-previous assessment comparison;
- authentication, tenant isolation and same-origin mutation protection;
- tenant workspace plans, usage and audit evidence;
- production runtime validation, host/proxy/request boundaries and readiness.

### Production-capable boundary, but deployment-specific work required

- single-region web runtime;
- SQLite identity and durable monitoring-job stores;
- supervised web/worker process model;
- SMTP integration boundary;
- filesystem backup/restore and migration procedures.

### Experimental or bounded observation

- deterministic AI crawler/readiness checks;
- static accessibility heuristics;
- passive public-security posture;
- engagement events that do not use pixels, cookies or fingerprinting.

### Intentionally deferred

See the strategic exclusions and severity review above.

## Review conclusion

The complete authenticated agency loop is now coherent:

```text
quick audit or captured lead
  -> explicit project conversion
  -> saved findings
  -> branded report and delivery
  -> remediation tasks
  -> monitoring rescan
  -> comparison evidence
```

Issue #87 can close when this document passes the repository quality gate. Browser onboarding and navigation consolidation remain separate, explicit product issues rather than hidden unfinished work inside the workflow review.
