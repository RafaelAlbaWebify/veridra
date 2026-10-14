# VERIDRA — Webify private operator application

VERIDRA is Webify's **private Windows-local application** for discovering and qualifying prospects, collecting bounded public-site evidence, preparing reports and proposals, managing client delivery and monitoring recurring Presence Care work. **It is not a SaaS product, customer portal, or application hosted for third parties.**

## Supported operating model

- Single Webify owner; only loopback listeners on the Windows workstation.
- Canonical startup: `VERIDRA_OPERATOR_START.bat` or `scripts/windows/veridra-local.ps1 operator-start`.
- Open `http://127.0.0.1:8010/agency`; use the operator launcher for start/status/stop/restart.
- Prospects and clients have separate, durable records; this is **not** SaaS workspace membership.
- Public-only discovery, assessment, reporting and monitoring require no credentials to a client's website.
- Hands-on remediation requires separate scope, authorization and safe access if contracted.
- Webify Presence Care uses **external Stripe/accounting authority**; VERIDRA stores bounded references and states. VERIDRA subscription tiers, workspace plans, seat quotas and SaaS Checkout are retired.
- Maintain verified local backups, an independent second copy and isolated recovery.

## Core workflow

`discover → qualify → audit → evidence review → outreach eligibility → reply/discovery → proposal → accepted terms/payment boundary → client/project → delivery/report → acceptance → Presence Care monitoring`

The initial market validation and first-customer legal/outreach gates remain at issues #297, #296 and #284. **No external outreach is authorized solely by installing or testing VERIDRA.**

## Technical and commercial boundaries

- Source-of-truth records use SQLite and local durable filesystem state. Existing `tenant_*` storage code may hold Webify client/project data; module names do not imply an active SaaS product.
- Bounded public checks cover crawl/indexability, SEO metadata, structured data, accessibility heuristics, AI crawler technical posture, trust/business signals and passive public security observations.
- Findings are **not** proof of universal AI visibility, lost revenue or accessibility compliance.
- VERIDRA is not a penetration-testing tool, website hosting platform, client password manager, accounting ledger or substitute for qualified legal/tax review.
- The separate legacy SaaS/cloud implementation is being **removed on the refactor branch**; obsolete modules and tests still present there are *not* approved product capabilities. See `.ai/DECISION_OPERATOR_ONLY_20261014.md`.
- Quality gates cover regression tests and operator-browser acceptance, but repository success alone does not prove outreach eligibility or readiness to charge a customer.

## Windows operator startup

```powershell
cd C:\Users\ralba\Documents\GitHub\veridra
.\VERIDRA_OPERATOR_START.bat
```

The current production-use pathway is **local and loopback-only**. Public SaaS deployment, tenant subscriptions, multi-company signup, hosted cloud infrastructure and team-seat administration are permanently out of scope.
