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

### 2. Hosted agency product — `VERIDRA_ENV=production`

The hosted runtime is the commercial product track adopted at the end of VERIDRA 12:

> A lower-cost agency website-audit / white-label / lead-generation product with broader website credibility coverage.

The hosted product reuses the same evidence engine and currently includes substantial foundations for:

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

The hosted track is **under active resurrection/productization and is not yet commercial-launch accepted**.

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

Initial hosted deployment is deliberately **single-host / single durable-volume**:

- one authoritative tenant-data volume;
- identity SQLite;
- tenant-scoped projects, assessments, reports, leads, usage and evidence;
- monitoring-job SQLite;
- separate web and monitoring-worker processes;
- quiesced cross-store backup plus independently durable off-host copies.

Horizontal/multi-node deployment is deferred until shared transactional persistence is introduced.

See `docs/operations/single-host-deployment.md` and `docs/operations/backup-restore.md`.

## Operator runtime

Supported local workflow:

    cd C:\Users\ralba\Documents\GitHub\veridra
    .\VERIDRA_OPERATOR_START.bat

or:

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\veridra-local.ps1 operator-start
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\veridra-local.ps1 operator-open

Default URL:

    http://127.0.0.1:8010/agency

## Hosted runtime

Production requires explicit durable paths, HTTPS origin/host policy, legal URLs and SMTP configuration. Stripe may remain absent during engineering/free-only validation, but real Stripe/provider acceptance is required before paid self-service plans are launched.

Use the `deployment/` single-host bundle as the current hosted MVP deployment starting point.

## Quality and readiness

Repository CI includes Ruff, strict mypy, pytest, deterministic checks and operator acceptance suites.

Evidence levels are tracked separately:

1. implemented;
2. regression-tested;
3. composed into the relevant runtime;
4. manually accepted in a realistic workflow;
5. externally/provider-validated where required.

A green repository does not by itself prove hosted commercial operability or first-customer operator readiness.

Current hosted resurrection status and gap classification live in:

- `.ai/SAAS_RESURRECTION_AUDIT.md`;
- `.ai/DECISIONS.md`;
- `docs/product/strategy-and-roadmap.md`.

## Safety boundary

VERIDRA collects bounded public evidence. It rejects unsafe/private targets and does not perform active exploitation, credential attacks, brute-force discovery, mail-server probing or penetration testing.

Accessibility findings are heuristics, not conformance certification. AI-readiness/crawler findings do not prove actual model visibility.
