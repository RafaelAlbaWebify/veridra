# Veridra

Veridra helps agencies find website risks and growth opportunities, turn them into branded client reports and remediation work, and prove improvements through recurring monitoring.

It audits technical SEO, AI technical readiness, AI crawler policy, trust, accessibility and passive public security; captures audit leads; produces evidence-backed white-label reports; converts findings into work; and monitors the results.

## Product boundary

Veridra is an agency website-audit, evidence, lead-generation, remediation and monitoring platform. It is not:

- a full Semrush alternative;
- a proprietary keyword, backlink, traffic-estimation or global rank-tracking database;
- a penetration-testing tool;
- proof of universal AI visibility;
- a replacement for licensed SEO-market data.

The core evidence model is:

> Observation → evidence → affected URLs → business impact → recommended fix → task → rescan verification.

## Implemented

- bounded public website assessment with DNS/IP validation, pinned connections, redirect revalidation and response-size limits;
- configurable multi-page crawl profiles with same-origin controls, sitemap discovery and page-level evidence;
- findings covering technical SEO fundamentals, AI crawler policy, AI technical readiness, trust, accessibility heuristics, domain/email posture and passive public security;
- authenticated users, tenants, memberships, roles, invitations, browser sign-in, password recovery/reset and server-side sessions;
- production transactional password-reset email through verified TLS SMTP, with generic recovery responses and reset tokens excluded from durable delivery evidence;
- tenant-qualified projects, leads, lead forms, remediation tasks, monitoring configuration, report profiles, assessments and report artifacts;
- explicit conversion from completed quick audits or qualified leads into tenant-qualified client projects;
- tenant-native lead-form creation, editing and deletion with tenant binding, plus lead qualification, ownership, notes and follow-up management;
- project-attached remediation task creation and management from saved findings;
- white-label report-profile creation and in-place editing, plus branded HTML, PDF and evidence-ZIP generation from tenant-qualified project data;
- durable monitoring jobs with idempotent enqueueing, worker leases, stale-lease recovery, bounded retries and a separate worker CLI;
- plan feature, usage and user-seat entitlement enforcement, including downgrade behavior;
- a provider-neutral subscription authority that can project authenticated external subscription events into tenant plan, status and billing-cycle entitlements with idempotency, ordering checks and durable evidence;
- health/readiness endpoints, trusted hosts, explicit proxy boundaries, bounded request bodies and fail-closed production runtime validation;
- an agency workflow home that separates temporary quick audits from persistent client projects and exposes only tenant-qualified normal-user operations;
- deterministic comparisons, history, evidence packages and CI validation.

## Verification status

The repository quality gate includes Ruff, strict mypy, pytest, a deterministic repository audit, a Chromium browser audit and an isolated commercial-acceptance journey.

The commercial acceptance runner exercises onboarding, Agency entitlement, a client project, branded HTML/PDF output, a tenant-bound lead form and public preview, lead qualification/follow-up, remediation-task creation/management and monitoring. It captures browser evidence and fails on false checks or unexpected request failures.

These checks verify repository behavior; they do not replace deployment-specific acceptance testing or an independent security assessment.

## Production foundation and remaining deployment work

The application provides explicit development, test and production modes; mandatory durable paths and trusted origins in production; trusted-host and proxy boundaries; bounded request bodies; health/readiness endpoints; browser authentication/recovery; transactional SMTP password-reset delivery; and separate web and monitoring-worker processes.

The composed runtime exposes the tenant-native agency and API workflow rather than the old standalone global browser trees. Compatibility router modules remain in the repository for isolated migration or compatibility use.

A controlled `veridra-subscription-apply` command provides the provider-neutral entitlement projection boundary. It does not authenticate provider webhooks or collect payment; a payment-provider adapter must verify provider events before invoking this authority.

A concrete hosted environment still requires infrastructure provisioning, TLS termination, process supervision, backups, monitoring, secrets management and deployment-specific validation. A real SMTP provider/account still has to be selected and configured. Payment collection, provider webhook authentication and customer-facing subscription management are not complete. Invitation delivery remains token/API-oriented rather than a complete customer email/browser acceptance journey.

## Important AI terminology

- **AI technical readiness:** whether content is accessible, structured, identifiable and technically understandable.
- **AI crawler policy:** whether named crawlers are allowed or blocked.
- **Sampled AI visibility:** whether selected AI providers mention or cite a business for a controlled prompt set.

Robots.txt checks, structured data and extractability do not prove actual AI visibility.

## Run locally

Direct Python/runtime setup:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m veridra.audit
.\.venv\Scripts\veridra-api.exe
```

The direct development runtime defaults to `http://127.0.0.1:8000` through `VERIDRA_BIND_PORT`.

For the packaged Windows operational workflow, use the root helper scripts such as:

```powershell
.\VERIDRA_SETUP.bat
.\VERIDRA_START.bat
.\VERIDRA_STATUS.bat
.\VERIDRA_OPEN.bat
```

The Windows launcher defaults to `http://127.0.0.1:8010` to avoid common local conflicts. Override it with `VERIDRA_LOCAL_PORT` when needed.

Browser sign-in is served at `/login`; password recovery starts at `/forgot-password`, and reset emails point to `/reset-password?token=...` on the configured trusted origin.

Production configuration is documented in `docs/operations/production-deployment.md` and `docs/architecture/production-runtime-hardening.md`.

## Safety boundary

Veridra collects bounded public evidence. It rejects private or non-public targets before website requests and does not perform active exploitation, credential attacks, subdomain brute force, mail-server probing or penetration testing.

Passive security findings describe observable public posture only. Accessibility findings are heuristics, not conformance certification. AI-readiness and crawler-policy findings are not claims of universal AI visibility.

## Current product priority

The authenticated agency workflow now covers the original commercial parity path: audit → project → white-label report → lead capture/qualification → remediation → monitoring/proof of improvement.

The next coherent priority is deployment and commercial hardening rather than another broad feature layer: complete invitation email/browser acceptance, integrate an authenticated payment-provider adapter with the subscription authority, provision and validate a hosted environment, and finish deployment-specific secrets, backups and monitoring.
