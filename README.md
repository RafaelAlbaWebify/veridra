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
- configurable multi-page crawl profiles with same-origin controls and page-level evidence;
- findings covering technical SEO fundamentals, crawlability, indexability, AI crawler policy, AI technical readiness, trust, accessibility heuristics, domain/email posture and passive public security;
- authenticated users, tenants, memberships, roles, invitations, password recovery and server-side sessions;
- tenant-qualified projects, leads, lead forms, remediation tasks, monitoring configuration, report profiles, assessments and report artifacts;
- white-label HTML, PDF and evidence-ZIP generation from tenant-qualified project data;
- durable monitoring jobs with idempotent enqueueing, worker leases, stale-lease recovery, bounded retries and a separate worker CLI;
- health/readiness endpoints, trusted hosts, explicit proxy boundaries, bounded request bodies and fail-closed production runtime validation;
- deterministic comparisons, history, evidence packages and CI validation.

## Locally verified

The repository test and audit stack covers:

- Ruff;
- strict mypy;
- pytest;
- deterministic repository audit;
- Chromium browser audit;
- tenant-isolation and authorization tests;
- durable worker and runtime-hardening tests.

These checks verify the repository implementation. They are not a substitute for deployment-specific acceptance testing or an independent security assessment.

## Production-ready foundation

The merged foundation provides:

- explicit `development`, `test` and `production` runtime modes;
- mandatory production identity database, tenant-data root, trusted HTTPS origin and allowed hosts;
- configurable bind host and port;
- non-disclosing `/health` and dependency-aware `/ready` endpoints;
- trusted-host enforcement;
- forwarded-header rejection from untrusted peers;
- request-body limits before route parsing;
- separate bounded web and monitoring-worker process model;
- deployment guidance for permissions, backups, migrations, supervision and secret redaction.

A concrete production environment still requires infrastructure provisioning, process supervision, TLS termination, backups, monitoring, SMTP configuration and deployment-specific validation.

## Experimental or incomplete

- the complete non-technical agency operator journey is under review;
- client-facing dashboards and secure report links need workflow validation;
- lead-to-project conversion and finding-to-task automation need commercial-flow review;
- entitlement and plan visibility are not yet a finished billing system;
- sampled AI visibility is not implemented as a production feature;
- optional external-data integrations remain future work.

## Intentionally deferred

Veridra will not build proprietary market-scale datasets internally, including:

- keyword databases or search-volume estimation;
- backlink crawling or backlink indexes;
- competitor traffic estimation;
- global rank-tracking infrastructure;
- paid-search intelligence;
- generic AI article generation;
- market-scale AI prompt databases;
- unverifiable universal authority, credibility or AI-visibility scores.

External data may later enrich reports through provider-neutral integrations. Every external metric must retain provider, timestamp, geography/database, device where applicable, freshness, limitations, usage cost and source attribution.

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

## Next milestone

The next milestone is an end-to-end agency workflow review covering onboarding, workspace setup, projects, crawl profiles, audit execution, finding review, report configuration, delivery, lead capture, lead conversion, remediation tasks, monitoring, rescans, comparisons, permissions and audit trail.

See issue #87 and `docs/product/strategy-and-roadmap.md`.