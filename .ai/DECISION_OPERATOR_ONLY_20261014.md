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

The `deployment/` and `infra/hetzner/` trees, six unused SaaS routers, hosted-only acceptance tests and tools, and historical hosted-product docs have been physically deleted on this branch. The shared entitlement/workspace policy and Stripe SaaS data/provider modules **still exist** and require dependency-aware retirement before the decision can be marked IMPLEMENTED. No full operator acceptance has been run after this removal.

## Follow-up cleanup — 2026-10-14

Commit `2c34ec0` physically removed the orphaned VERIDRA SaaS runtime-billing adapter and signup legal-evidence helper, together with three obsolete tests. These were not Webify Presence Care Stripe services. The remaining `stripe_billing.py` and `subscription_authority.py` cannot yet be deleted safely: historical H6/provider snapshots, offboarding and production preflight still import them. `tenant_signup.py` also feeds identity-email handling and requires dependency disentanglement. Do not treat this incremental removal as completed refactoring or a validated operator release.

## Dependency review — 2026-10-14

- Removed `local_provider_snapshot.py` and its test at `e26a866`: these read SaaS workspace-plan and Stripe Checkout-reservation state, not Webify Presence Care accounting references.
- `production_preflight.py` still imports `StripeBillingConfig` from the abandoned SaaS adapter. It must be rewritten to test Webify-specific provider boundaries before deleting `stripe_billing.py`.
- `tenant_offboarding.py` still consults `StripeTenantBindingStore`; retain safety checks or replace with a read-only compatibility migration before removing the old store.
- Multiple agency routes still import `tenant_entitlements` and `tenant_workspace_policy`. Replace quota/plan gating with explicitly local-operator permissions and regression tests before deleting the policy modules.
- This branch is **NOT VALIDATED FOR DEPLOYMENT** and has no fresh full preflight after module removal; do not merge into `main` until the imports and operator UI are validated.

## October 15 — Retired SaaS provider code physically deleted

- `de7b925`: removed legacy `stripe_billing.py`, `subscription_authority.py`, SaaS webhook verification, local H6 acceptance phases and SaaS provider-reconciliation modules with their corresponding tests. These implement VERIDRA workspace subscriptions, **not** Webify Presence Care provider reference/mirror accounting.
- `f9f3369`: removed nine obsolete SaaS H6/Checkout/Stripe Windows launchers and launcher-contract test. Kept `VERIDRA_STRIPE_MIRROR_ACCEPTANCE.bat`, `tools/operator_stripe_mirror_acceptance.py`, Presence Care acceptance documents and provider evidence.
- This still needs a complete static-import scan **on the current branch**, Ruff/mypy/pytest and Windows operator browser testing before integration. Existing `workspace_policy`, `tenant_entitlements` and local-commercial Windows launcher code still need simplification; historic tests and documentation need reconciliation.
