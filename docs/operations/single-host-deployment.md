# VERIDRA single-host deployment bundle

Status: **SUPPORTED HOSTED MVP ARCHITECTURE — NOT YET COMMERCIAL-LAUNCH ACCEPTED**

The `deployment/` Docker Compose + Caddy bundle is the retained starting point for the hosted `VERIDRA_ENV=production` product. It is intentionally a single-host architecture: one durable VERIDRA volume, one web process boundary, scheduled monitoring-worker execution and an HTTPS reverse proxy.

This does **not** replace the Webify operator deployment and does not make hosted production automatically ready for customers.

## Two supported product tracks

### Webify operator

`VERIDRA_ENV=operator` remains the private Webify workflow:

- Windows operator application;
- loopback / `127.0.0.1`;
- no public signup;
- no public SaaS billing;
- no inbound embedded lead forms;
- no customer access to VERIDRA.

See `docs/WINDOWS_LOCAL_OPERATIONS.md` and the operator-readiness issues #279, #284 and #296.

### Hosted agency product

`VERIDRA_ENV=production` is the commercial agency-audit product track:

- HTTPS public application boundary;
- tenant-qualified signup/login and storage;
- plan/usage policy;
- white-label reports;
- embedded audit lead forms;
- tenant projects, remediation and monitoring;
- real tenant memberships;
- optional Stripe configuration during engineering, but Stripe/provider acceptance is required before a paid public launch.

The hosted product has its own launch gate and must not inherit operator-readiness claims.

## Initial scaling boundary

The hosted MVP is deliberately **single-host / single durable-volume**.

Durable state currently spans:

- identity SQLite;
- per-tenant filesystem state;
- workspace usage/reservation files;
- Stripe binding/subscription evidence when configured;
- monitoring-job SQLite under the tenant data root.

Those stores do not share one distributed transaction boundary. Therefore:

- do not run multiple independent web replicas against copied/local data;
- do not treat the current bundle as horizontally scalable;
- keep all writers on the same authoritative durable volume;
- use the existing file/SQLite locking and atomic-write boundaries;
- stop/quiesce writers for a consistent cross-store backup;
- keep independently durable off-host backups and periodically test restore.

See `docs/operations/backup-restore.md`.

## Deployment composition

The supplied bundle contains:

- `web`: VERIDRA production runtime;
- `worker`: bounded monitoring-worker execution;
- `caddy`: HTTPS reverse proxy;
- `veridra_data`: authoritative durable application state.

Production still requires explicit configuration for identity storage, tenant storage, trusted HTTPS origin, allowed hosts, legal URLs and SMTP. Billing configuration is additionally required before enabling paid self-service plans.

## Acceptance boundary

Repository support is not proof that a public deployment is ready.

Before commercial launch, the hosted track must separately prove:

1. production startup/preflight;
2. signup -> verified login -> workspace;
3. plan entitlements and usage enforcement;
4. project audit -> report/PDF -> remediation -> monitoring;
5. embedded lead form -> tenant lead -> project conversion;
6. membership invitation/seat enforcement;
7. Stripe test-mode checkout, webhook, downgrade/cancellation and portal lifecycle;
8. backup -> isolated restore -> application/provider reconciliation;
9. TLS/proxy/security-header and external-provider behavior on the actual host;
10. final human acceptance of the customer-facing workflow.

Until those gates are complete, this bundle is a supported architecture artifact, not evidence of commercial operability.
