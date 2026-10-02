# VERIDRA product strategy and roadmap

## Canonical product position

VERIDRA now has two supported product tracks over the same bounded-evidence core.

### Webify operator

`VERIDRA_ENV=operator` remains Webify's private operator application.

Its commercial purpose is to help Webify:

1. discover and qualify businesses;
2. collect bounded public evidence;
3. apply outreach/compliance gates;
4. progress proposals/customers;
5. deliver remediation/reporting;
6. operate Presence Care where justified;
7. prove changes through reassessment.

Operator readiness and real outreach remain governed by the dedicated Webify gates (#279, #284, #296).

### Hosted VERIDRA agency product

`VERIDRA_ENV=production` is the separate SaaS product track.

Target position:

**A lower-cost white-label website-audit and lead-generation product for agencies, freelancers and website-service businesses, with broader credibility coverage than a conventional SEO audit alone.**

Primary buyer groups:

- web-design / SEO / marketing agencies;
- WordPress maintenance providers;
- MSP / IT consultants;
- hosting / website-service providers;
- lead-generation businesses.

## Hosted commercial loop

1. agency creates/verifies a workspace;
2. chooses plan/capacity;
3. creates a client project or embedded audit form;
4. VERIDRA performs a bounded multi-page audit;
5. findings expose evidence and affected URLs;
6. agency prepares a branded report;
7. inbound audit form can capture a prospect into the tenant lead pipeline;
8. won lead becomes a client project;
9. findings become remediation work;
10. reassessment/monitoring proves improvement.

## Required hosted parity

Initial commercial parity target:

- bounded multi-page crawl and page-level findings;
- affected-page evidence;
- white-label report profiles;
- professional HTML/PDF output;
- embedded audit/lead form;
- tenant lead management;
- client projects;
- remediation/task workflow;
- recurring monitoring/comparison;
- plan quotas and tenant seats;
- self-service subscription lifecycle.

## VERIDRA differentiators

Keep the product broader than basic SEO audit software through bounded evidence for:

- passive security and email-domain posture;
- trust/business credibility;
- AI technical readiness/crawler policy;
- accessibility heuristics;
- detailed technical/page-level evidence.

Do not claim capabilities VERIDRA does not possess.

## Explicit initial exclusions

Do not make initial launch dependent on:

- Ahrefs-scale backlink intelligence;
- Semrush-scale keyword databases;
- global rank tracking;
- competitor traffic estimates;
- active vulnerability scanning;
- enterprise collaboration suites;
- complex marketing automation;
- horizontal/multi-node application deployment;
- custom domains;
- report-open / CTA-click analytics.

These may be reconsidered only when commercial evidence justifies them.

## Runtime and persistence boundary

Hosted MVP is single-host/single durable-volume.

Current persistence is SQLite + tenant filesystem state. Web and monitoring worker remain separate bounded processes. Cross-store backups require quiescing writers and must be copied to independent storage.

Horizontal scaling requires a later persistence redesign.

## Current hosted resurrection sequence

### H0 — SaaS resurrection audit — COMPLETE

Audit every retained SaaS capability as:

- KEEP;
- REWORK;
- MISSING;
- REMOVE.

Evidence lives in `.ai/SAAS_RESURRECTION_AUDIT.md`. Closure baseline: CI run 36990112480 / head 4250c769.

### H1 — Core commercial integrity — COMPLETE

Close entitlement, quota, tenant-isolation and workflow bypasses across:

- audits/crawled pages;
- projects;
- report profiles;
- PDF/export;
- monitoring;
- embedded lead forms;
- lead conversion;
- memberships.

Closure evidence: `.ai/HOSTED_H1_ACCEPTANCE.md`; CI run 36990700714 / head f65f4caa.

### H2 — Commercial product UX — COMPLETE

Converge authenticated navigation around:

- Home;
- Audits / Projects;
- Leads;
- Lead Forms;
- Reports / Monitoring;
- Team;
- Plan / Billing.

Hide or clearly lock plan-unavailable features rather than exposing raw 403/429 experiences.

Closure evidence: `.ai/HOSTED_H2_ACCEPTANCE.md`; CI run 36998742301 / head fd31827e.

### H3 — Report polish — COMPLETE

Improve professional output without rebuilding the evidence engine:

- reusable branded templates;
- cover polish;
- table of contents;
- charts/summary visualization where useful;
- reliable page breaks;
- report preview.

Closure evidence: `.ai/HOSTED_H3_ACCEPTANCE.md`; CI run 37001235636 / code head 09cf905f.

### H4 — Audit scale/productization — COMPLETE

Current named crawl profiles top out at 100 pages.

Before increasing scale:

- move larger crawls away from long synchronous HTTP requests;
- define job/progress state;
- model plan page budgets and concurrency;
- test 500-page and larger workloads safely.

Do not merely raise hard caps.

Closure evidence: `.ai/HOSTED_H4_ACCEPTANCE.md`; CI run 37005555931 / code head b730c7af. Customer-facing Deep remains capped at 100 pages after H4.

### H5 — Lead-generation product polish — COMPLETE

Productize the already-existing tenant lead form:

- embed setup UX;
- form branding;
- plan/upgrade guidance;
- reliable origin/rate-limit behavior behind the production proxy;
- lead pipeline ergonomics;
- conversion/report attribution.

Closure evidence: `.ai/HOSTED_H5_ACCEPTANCE.md`; CI run 37006643458 / head bf176450.

### H6 — Paid hosted provider acceptance — ACTIVE

Prove on real test providers:

- SMTP sender/delivery;
- Stripe test-mode Checkout;
- verified webhook projection;
- upgrade/downgrade;
- payment failure/suspension;
- portal management;
- cancellation;
- reconciliation after backup/restore.

### H7 — Hosted deployment acceptance

Prove the real single-host deployment:

- HTTPS/Caddy boundary;
- production startup/preflight;
- signup/login;
- tenant isolation;
- end-to-end audit/report/lead/monitoring workflows;
- worker scheduling;
- off-host backup;
- isolated restore;
- provider reconciliation;
- final human acceptance.

## Completion rule

Implementation presence is not launch readiness.

Hosted VERIDRA becomes launch-eligible only when the product workflow is regression-tested **and** manually/provider-validated on the actual hosted stack.

Operator readiness and hosted launch readiness are intentionally separate measurements.
