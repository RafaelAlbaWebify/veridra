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
```

Set `VERIDRA_TRUSTED_PROXY_IPS` only when a reverse proxy connects directly to the application. List only immediate proxy IP addresses. Forwarded headers from every other peer are rejected, and Uvicorn proxy-header interpretation remains disabled.

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

- read/write access to the identity database and its parent directory;
- read/write access to the tenant-data root;
- no write access to application source or package files;
- no interactive login unless operationally required.

Do not place durable data inside an ephemeral container layer or temporary checkout.

## Startup and migration order

1. Stop web and worker processes before restoring or manually migrating data.
2. Back up the identity database and tenant-data root together.
3. Start one web process to apply versioned identity migrations.
4. Confirm `/health` returns `200` and `/ready` returns `200`.
5. Start the remaining web processes.
6. Resume scheduled worker invocations.

A `503` readiness response means a configured durable dependency is unavailable. It intentionally does not disclose paths or database details.

## Backup and recovery

Back up these assets as one consistency set:

- identity SQLite database;
- tenant project, lead, assessment, report-profile and delivery data;
- durable monitoring-job SQLite database.

Test restoration in an isolated environment. A backup that has not been restored successfully is not considered verified.

During recovery, prevent workers from leasing jobs until the identity and tenant-data snapshots are both restored.

## Logging and secrets

Never log:

- session cookie values;
- password-reset or invitation tokens;
- `Authorization` headers;
- SMTP passwords;
- raw request bodies containing personal data;
- environment-variable dumps.

Operational logs may include bounded internal identifiers and generic error categories where needed, but should avoid combining tenant identifiers with unnecessary personal data.

## Supervision expectations

Configure the service manager to:

- restart the web process after unexpected exit with bounded backoff;
- run the monitoring worker on a fixed schedule;
- prevent overlapping worker starts unless intentional concurrency has been tested;
- capture stdout and stderr in protected logs;
- alert on repeated web restarts, readiness failures and terminal monitoring-job failures.

This repository does not prescribe systemd, Windows Services, Docker Compose, Kubernetes or a cloud-specific supervisor. Deployment tooling must preserve the same process and trust boundaries.

## Pre-release checklist

- production configuration validates without fallback defaults;
- public TLS and allowed host match `VERIDRA_TRUSTED_ORIGIN`;
- the application port is not directly internet-accessible;
- trusted proxy IPs contain only immediate proxies;
- `/health` and `/ready` are monitored separately;
- filesystem permissions use least privilege;
- backup and restore have been tested;
- identity migrations complete before worker scheduling resumes;
- secrets are supplied outside source control;
- log access is restricted;
- exact deployed commit and validation evidence are recorded.
