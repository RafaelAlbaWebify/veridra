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
- authenticated users, tenants, memberships, roles, invitations, password recovery and server-side sessions;
- tenant-qualified projects, leads, lead forms, remediation tasks, monitoring configuration, report profiles, assessments and report artifacts;
- white-label HTML, PDF and evidence-ZIP generation from tenant-qualified project data;
- durable monitoring jobs with idempotent enqueueing, worker leases, stale-lease recovery, bounded retries and a separate worker CLI;
- health/readiness endpoints, trusted hosts, explicit proxy boundaries, bounded request bodies and fail-closed production runtime validation;
- an agency workflow home that separates temporary quick audits from persistent client projects;
- deterministic comparisons, history, evidence packages and CI validation.

## Verification status

The repository quality gate includes Ruff, strict mypy, pytest, a deterministic repository audit and a Chromium browser audit. These checks verify repository behavior; they do not replace deployment-specific acceptance testing or an independent security assessment.

## Production foundation and remaining deployment work

The application provides explicit development, test and production modes; mandatory durable paths and trusted origins in production; trusted-host and proxy boundaries; bounded request bodies; health/readiness endpoints; and separate web and monitoring-worker processes.

A concrete hosted environment still requires infrastructure provisioning, TLS termination, process supervision, backups, monitoring, SMTP configuration, secrets management and deployment-specific validation. Billing collection and subscription lifecycle management are not complete.

## Important AI terminology

- **AI technical readiness:** whether content is accessible, structured, identifiable and technically understandable.
- **AI crawler policy:** whether named crawlers are allowed or blocked.
- **Sampled AI visibility:** whether selected AI providers mention or cite a business for a controlled prompt set.

Robots.txt checks, structured data and extractability do not prove actual AI visibility.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m veridra.audit
.\.venv\Scripts\veridra-api.exe
```

Development defaults bind to `http://127.0.0.1:8000`.

Production configuration is documented in `docs/operations/production-deployment.md` and `docs/architecture/production-runtime-hardening.md`.

## Safety boundary

Veridra collects bounded public evidence. It rejects private or non-public targets before website requests and does not perform active exploitation, credential attacks, subdomain brute force, mail-server probing or penetration testing.

Passive security findings describe observable public posture only. Accessibility findings are heuristics, not conformance certification. AI-readiness and crawler-policy findings are not claims of universal AI visibility.

## Current product priority

The first agency workflow shell is implemented. The next coherent milestone is explicit conversion from a completed quick audit into a tenant-qualified client project, followed by project-attached finding-to-task and report-delivery workflows.

See issue #87 and `docs/product/agency-operator-workflow-audit.md`.
