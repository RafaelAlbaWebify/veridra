# VERIDRA Architecture

## Runtime
```mermaid
flowchart LR
  Browser --> FastAPI[FastAPI web/API]
  FastAPI --> Identity[(SQLite identity/session data)]
  FastAPI --> Tenant[(Filesystem tenant/project state)]
  FastAPI --> Assessment[Assessment/evidence engine]
  FastAPI --> Reports[HTML/PDF/evidence reports]
  FastAPI --> Billing[Subscription authority / Stripe adapter]
  FastAPI --> SMTP[SMTP identity/report email]
  Worker[Monitoring worker] --> Tenant
  Worker --> Assessment
  Edge[DNS/TLS/reverse proxy] --> FastAPI
```

## Major components
1. **Assessment/evidence** — crawling, DNS/IP safety validation, SEO, AI-readiness/crawler policy, trust, accessibility heuristics, passive public security.
2. **Acquisition/prospecting** — discovery/evidence/qualification/visual outreach/local competitive/review-intelligence tooling.
3. **Agency/commercial lifecycle** — authenticated browser workflow for prospects, leads, deals, proposals, customers, projects, tasks, change requests, delivery and recurring lifecycle.
4. **Identity/billing** — signup, email verification, password recovery, invitations, memberships/roles, entitlements, subscription authority, Stripe adapter.
5. **Monitoring/reporting** — report profiles/artifacts, comparisons, monitoring jobs/worker, report delivery.
6. **Production/ops** — runtime validation, trusted hosts/proxy, security headers, access logging, backup/restore, ops checks, deployment acceptance, tenant offboarding.

## Persistence
Current model is SQLite + filesystem tenant state. It is intentionally treated as **single-writer** for production until a shared persistence/concurrency redesign is implemented and tested.

## External interfaces
- SMTP provider: required in production; provider not yet selected/verified for first-customer deployment.
- Stripe: adapter implemented; external resources not yet production/test-provider verified.
- Public DNS/TLS/reverse proxy/compute/storage/secret manager: deployment responsibilities, not provisioned by repository.

## Trust/security boundaries
- assessment targets must be public and pass DNS/IP/redirect safety validation;
- no active exploitation/credential attacks/mail probing;
- production hides FastAPI schema/docs and legacy onboarding/health aliases;
- trusted HTTPS origin/host/proxy config fail closed;
- customer secrets/PHI/card data are outside ordinary operational storage;
- external provider state controls billing truth; VERIDRA mirrors operational state.

## Known weaknesses
- single-writer persistence limits horizontal scaling;
- many web workflow modules live in one Python package, so logical module contracts are documentary rather than package-enforced;
- provider-neutral deployment means environment provisioning is external/manual;
- production operability remains unproven until external gates pass.

See `docs/modules/*.CONTRACT.md`, `docs/operations/`, `README.md`.