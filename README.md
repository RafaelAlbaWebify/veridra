# VERIDRA

VERIDRA is an evidence-backed digital-presence assessment, reporting, lead-generation and client-delivery platform with two deliberately separate runtime products over a shared core.

## Product tracks

### 1. Webify operator — `VERIDRA_ENV=operator`

The operator runtime is Webify's private application for Rafael's own service workflow:

- Windows operator-local;
- loopback-only;
- one Webify owner;
- no browser login in the normal workflow;
- no public signup;
- no SaaS subscription plans, team seats or embedded inbound lead forms;
- no public hosting requirement.

Primary workflow:

`discover → qualify → audit → outreach eligibility → conversation → proposal → customer/work-start gate → project → delivery → acceptance → Presence Care/proof`

The operator readiness gates and first-customer work remain tracked separately by #279, #284 and #296.

### 2. Commercial agency product — `VERIDRA_ENV=production` (local-first)

The commercial runtime is the agency product track adopted at the end of VERIDRA 12. For the current phase it runs locally on Rafael's Windows PC over loopback; public hosting is deferred:

> A lower-cost agency website-audit / white-label / lead-generation product with broader website credibility coverage.

The commercial product reuses the same evidence engine and currently includes substantial foundations for:

- public signup and verified browser identity;
- tenant-qualified storage and roles;
- Free / Solo / Professional / Agency workspace policy;
- project, audit and crawl usage enforcement;
- white-label report profiles;
- HTML/PDF/evidence reporting;
- remediation tasks;
- recurring monitoring and comparison;
- embedded tenant-bound audit lead forms;
- lead management and lead-to-project conversion;
- team memberships and seat limits;
- Stripe Checkout/Portal/webhook subscription projection.

The commercial track is **under active local productization and is not yet commercially accepted**. Its multi-tenant/SaaS-capable code is retained, but external hosting is not a current readiness gate.

## Evidence boundary

VERIDRA performs bounded public checks covering:

- technical SEO and crawl/indexability fundamentals;
- page-level metadata and affected-URL evidence;
- AI crawler policy / technical readiness;
- trust, business and contact signals;
- accessibility heuristics;
- passive public security and email-domain posture;
- structured-data and page-level observations.

VERIDRA is not:

- a penetration-testing product;
- a Semrush/Ahrefs-style backlink, traffic or keyword database;
- proof of universal AI visibility;
- an accounting ledger;
- a substitute for provider/payment authority.

## Shared architecture

Current persistence uses SQLite plus tenant filesystem state.

The current commercial deployment target is **local single-machine / loopback** on Rafael's Windows PC:

- one authoritative tenant-data root;
- identity SQLite;
- tenant-scoped projects, assessments, reports, leads, usage and evidence;
- durable monitoring/crawl-job SQLite state;
- separate bounded web/worker processes where applicable;
- quiesced backup plus an independent operator-controlled second copy.

The existing single-host/Caddy deployment bundle is retained for a future public-hosting phase, but it is not a current operability gate.

See `docs/operations/backup-restore.md`.

## Operator runtime

Supported local workflow:

    cd C:\Users\ralba\Documents\GitHub\veridra
    .\VERIDRA_OPERATOR_START.bat

or:

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\veridra-local.ps1 operator-start
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\veridra-local.ps1 operator-open

Default URL:

    http://127.0.0.1:8010/agency

## Commercial local runtime

`VERIDRA_ENV=production` enables the commercial agency feature set. In the current phase it is allowed to run over HTTP only when both bind host and trusted origin are explicit loopback-local values such as `127.0.0.1`.

Any future non-loopback/public production deployment still requires HTTPS and a separate hosting acceptance phase.

Stripe may remain absent during free-only/local engineering. Stripe test-mode acceptance is required before paid local commercial workflows are treated as proven. SMTP remains optional unless automation is enabled.

## Quality and readiness

Repository CI includes Ruff, strict mypy, pytest, deterministic checks and operator acceptance suites.

Evidence levels are tracked separately:

1. implemented;
2. regression-tested;
3. composed into the relevant runtime;
4. manually accepted in a realistic workflow;
5. externally/provider-validated where required.

A green repository does not by itself prove commercial local operability or first-customer operator readiness.

Current commercial product status and gap classification live in:

- `.ai/SAAS_RESURRECTION_AUDIT.md`;
- `.ai/DECISIONS.md`;
- `docs/product/strategy-and-roadmap.md`.

## Safety boundary

VERIDRA collects bounded public evidence. It rejects unsafe/private targets and does not perform active exploitation, credential attacks, brute-force discovery, mail-server probing or penetration testing.

Accessibility findings are heuristics, not conformance certification. AI-readiness/crawler findings do not prove actual model visibility.
