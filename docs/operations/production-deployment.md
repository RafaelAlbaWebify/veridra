# Production deployment operations

## Process model

Run the web application and durable monitoring worker as separate supervised processes.

Web process:

```text
veridra-api
```

Worker invocation:

```text
veridra-monitoring-worker --limit 10
```

The worker is intentionally bounded and exits. Use an operating-system scheduler or process supervisor to invoke it repeatedly. Do not embed an infinite worker loop inside the web process.

## Required production configuration

Set these values explicitly:

```text
VERIDRA_ENV=production
VERIDRA_IDENTITY_DB=/absolute/durable/path/identity.sqlite3
VERIDRA_TENANT_DATA_ROOT=/absolute/durable/path/tenants
VERIDRA_TRUSTED_ORIGIN=https://app.example.com
VERIDRA_ALLOWED_HOSTS=app.example.com
VERIDRA_BIND_HOST=127.0.0.1
VERIDRA_BIND_PORT=8000
VERIDRA_MAX_REQUEST_BODY_BYTES=1000000

VERIDRA_SMTP_HOST=smtp.example.com
VERIDRA_SMTP_PORT=587
VERIDRA_SMTP_ENCRYPTION=starttls
VERIDRA_SMTP_SENDER=security@example.com
VERIDRA_SMTP_SENDER_NAME=Veridra
```

If the SMTP provider requires authentication, also set:

```text
VERIDRA_SMTP_USERNAME=<provider-user>
VERIDRA_SMTP_PASSWORD=<secret>
```

`VERIDRA_SMTP_PASSWORD_ENV` may name a different environment variable containing the password. The password itself is never part of `SmtpConfig` or durable delivery-attempt evidence.

Production startup fails closed when SMTP host/sender configuration is missing, when SMTP configuration is invalid, or when a username is configured without its password secret. Development and test environments may run without SMTP.

Only STARTTLS and implicit TLS modes are supported. SMTP uses the operating system/Python CA trust store for certificate verification and has a bounded connection timeout.

Set `VERIDRA_TRUSTED_PROXY_IPS` only when a reverse proxy connects directly to the application. List only immediate proxy IP addresses. Forwarded headers from every other peer are rejected, and Uvicorn proxy-header interpretation remains disabled.

## Browser authentication and password recovery

The composed runtime exposes browser authentication at `/login`, password-recovery request at `/forgot-password`, and one-time password reset at `/reset-password`.

Browser sign-in reuses the same durable password authenticator, login throttling and server-side session lifecycle as the API. Successful sign-in issues the existing secure session cookie and redirects to `/agency`. Unsafe browser authentication operations enforce `VERIDRA_TRUSTED_ORIGIN`.

Password recovery is wired to the configured SMTP transport. Existing and missing accounts receive the same generic browser response so the flow does not disclose whether an account exists. A valid request for an active account sends an absolute reset link derived from `VERIDRA_TRUSTED_ORIGIN`.

Reset pages and login pages return `Cache-Control: no-store`, `Referrer-Policy: no-referrer` and `X-Frame-Options: DENY`. The reset token is carried only in the one-time email link/form and in the existing password-recovery token store as a digest; it is not written to identity-email delivery evidence. Successful reset revokes existing sessions and makes the token unusable again through the existing recovery service.

Identity-email attempts are written beside the identity database under `identity-email-deliveries/`. Evidence records recipient, status, subject, message digest and a one-way delivery key. SMTP or delivery-evidence failures do not alter the public recovery response; alert operationally on failed identity-email attempts.

## Subscription authority boundary

Production users cannot apply local plan overrides. Subscription-driven entitlement changes must come through a controlled billing integration.

The provider-neutral projection command is:

```text
veridra-subscription-apply \
  --tenant-id <tenant-id> \
  --provider <provider-key> \
  --event-id <verified-provider-event-id> \
  --subscription-id <provider-subscription-id> \
  --plan <free|solo|professional|agency> \
  --status <active|suspended> \
  --cycle-anchor-day <1-28> \
  --occurred-at <timezone-aware-provider-timestamp>
```

This command is not a webhook verifier and is not a payment API. Invoke it only after a trusted adapter has authenticated the provider event and mapped provider-specific subscription states into Veridra's plan/status model.

The authority:

- keeps provider event identity and subscription identity as evidence;
- rejects a provider event ID reused with different data;
- treats exact event replay as idempotent;
- rejects stale or timestamp-ambiguous events rather than silently overwriting newer state;
- preserves the tenant workspace display name while projecting plan, status and cycle anchor;
- rolls back the workspace projection if durable subscription-event evidence cannot be written.

Restrict execution of this command and write access to the tenant-data root to the billing integration/service account. Provider secrets, webhook signing secrets and raw payment payloads must not be passed through command-line arguments or stored in tenant workspace evidence.

## Reverse proxy boundary

Terminate public TLS at a controlled reverse proxy. The proxy should:

- connect to Veridra over a private or loopback interface;
- set the public `Host` consistently;
- enforce its own request and connection limits;
- replace, rather than append blindly to, forwarded headers;
- prevent direct public access to the application bind port.

The application does not use forwarded headers to redefine the ASGI scheme, host or client identity. Trusting a proxy IP permits those headers to pass the boundary for controlled upstream use; it does not make arbitrary client-supplied values authoritative.

## Filesystem permissions

Use a dedicated service account. Grant it:

- read/write access to the identity database, identity-email delivery evidence and their parent directory;
- read/write access to the tenant-data root;
- no write access to application source or package files;
- no interactive login unless operationally required.

Do not place durable data inside an ephemeral container layer or temporary checkout.

## Startup and migration order

1. Stop web and worker processes before restoring or manually migrating data.
2. Back up the identity database, identity-email delivery evidence and tenant-data root together.
3. Start one web process to apply versioned identity migrations and validate SMTP configuration.
4. Confirm `/health` returns `200` and `/ready` returns `200`.
5. Confirm browser sign-in and a controlled password-reset delivery against the public trusted origin.
6. Start the remaining web processes.
7. Resume scheduled worker invocations.

A `503` readiness response means a configured durable dependency is unavailable. It intentionally does not disclose paths or database details.

## Backup and recovery

Back up these assets as one consistency set:

- identity SQLite database;
- identity-email delivery evidence;
- tenant project, lead, assessment, report-profile and delivery data;
- tenant workspace policy, usage and subscription-event evidence;
- durable monitoring-job SQLite database.

Test restoration in an isolated environment. A backup that has not been restored successfully is not considered verified.

During recovery, prevent workers and billing integrations from writing tenant state until the identity and tenant-data snapshots are both restored.

## Logging and secrets

Never log:

- session cookie values;
- password-reset or invitation tokens;
- `Authorization` headers;
- SMTP passwords;
- payment-provider secrets or webhook signing secrets;
- raw request bodies containing personal or payment data;
- environment-variable dumps.

Operational logs may include bounded internal identifiers and generic error categories where needed, but should avoid combining tenant identifiers with unnecessary personal data.

## Supervision expectations

Configure the service manager to:

- restart the web process after unexpected exit with bounded backoff;
- run the monitoring worker on a fixed schedule;
- prevent overlapping worker starts unless intentional concurrency has been tested;
- capture stdout and stderr in protected logs;
- alert on repeated web restarts, readiness failures, failed identity-email attempts and terminal monitoring-job failures.

This repository does not prescribe systemd, Windows Services, Docker Compose, Kubernetes or a cloud-specific supervisor. Deployment tooling must preserve the same process and trust boundaries.

## Pre-release checklist

- production configuration validates without fallback defaults;
- public TLS and allowed host match `VERIDRA_TRUSTED_ORIGIN`;
- the application port is not directly internet-accessible;
- trusted proxy IPs contain only immediate proxies;
- SMTP TLS mode, sender identity and authentication secret are configured and tested;
- browser login enforces same-origin POSTs and issues the secure server-side session cookie;
- password-reset email contains the trusted-origin browser link and the token is absent from durable email evidence;
- existing and missing recovery requests remain indistinguishable to the browser client;
- `/health` and `/ready` are monitored separately;
- filesystem permissions use least privilege;
- backup and restore have been tested, including identity-email and subscription-event evidence;
- identity migrations complete before worker scheduling resumes;
- subscription-provider events are authenticated before entitlement projection;
- billing integration credentials and webhook secrets are supplied outside source control;
- secrets are supplied outside source control;
- log access is restricted;
- exact deployed commit and validation evidence are recorded.
