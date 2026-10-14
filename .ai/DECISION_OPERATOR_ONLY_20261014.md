# D-014 — VERIDRA is exclusively Webify's private operator tool

Status: **DECIDED 2026-10-14 / REMOVAL IN PROGRESS**

## Product boundary

VERIDRA serves Webify's own acquisition, evidence-backed assessment, proposal, customer/project management, report delivery and recurring Presence Care workflows on the operator's Windows PC. It is not and will not be commercialized as standalone SaaS. No third-party access to the VERIDRA application.

## Remove from active source, tests, packaging and instructions

- Public/cloud application deployment, VPS/Hetzner/Caddy/Compose/systemd/off-host host-management artifacts.
- Multi-company SaaS signup/login/onboarding, subscription tiers/plans, account and seat quotas, workspace-membership and team administration.
- VERIDRA SaaS Stripe plans, self-service billing and subscriptions. **Do not remove** the separately proven Stripe **Webify Presence Care** provider/reference/accounting workflow.
- SaaS-specific entitlements, quota metering, hosted-only forms/routes and acceptance suites, when not needed for the Webify operator.

## Retain

- Private operator-local loopback Windows launchers, process supervision, backups, restores and runtime safety.
- Customer/prospect/project data isolation and ownership checks wherever necessary for Webify's client records. A module named `tenant_*` does **not** automatically mean multi-company SaaS; inspect real callers before deleting.
- Public-web audits, crawling, assessments, reports/PDF, monitoring, AI analysis, CRM/proposals, project delivery, consent/suppression and legal gates.
- External service boundaries for Webify billing, accounting and optionally SMTP.

## Migration and verification rule

First remove independent historical infrastructure. Then remove hosted-only runtime wiring, modules and associated tests in dependency order, replacing SaaS tenant/account concepts with single-operator semantics only where behavior remains necessary. Make changes on `refactor/webify-operator-only`; do **not** merge incomplete intermediate steps. Verify Windows startup, local data compatibility, backup/recovery, prospect→proposal→delivery, report, monitoring, and Presence Care Stripe reference reconciliation. Preserve or migrate existing operator data; never silently discard live stores.

## Scope of the first removal commit

The `deployment/` and `infra/hetzner/` trees have been deleted from the branch. That is only the cloud/public deployment slice. The hosted SaaS code still exists and must be removed before this decision can be marked IMPLEMENTED.
