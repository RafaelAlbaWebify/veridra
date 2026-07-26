# Production runtime hardening

## Purpose

This milestone defines the fail-closed runtime boundary required to deploy Veridra's authenticated web application and durable monitoring worker without trusting implicit development defaults.

## Runtime environments

Veridra distinguishes `development`, `test` and `production` explicitly.

Development and test may use loopback binding and temporary local storage. Production must provide durable absolute paths, an HTTPS trusted origin and explicit host/proxy configuration.

## Startup contract

Production startup must refuse to continue when mandatory configuration is absent, malformed or unsafe. Validation covers at least:

- identity database path;
- tenant data root;
- trusted HTTPS application origin;
- allowed request hosts;
- bind host and port;
- reverse-proxy trust configuration;
- writable durable storage and database parent directories.

Configuration errors must identify the setting category without printing secrets or token values.

## Request boundary

The application rejects untrusted `Host` values before route handling. Forwarded headers are not trusted merely because they are present. Proxy-derived scheme, host or client information may be accepted only when the immediate peer matches an explicitly configured trusted proxy boundary.

Authenticated unsafe requests retain the existing trusted-origin validation. Public embedded audit routes retain their independent allowed-origin policy.

Request bodies are bounded before application parsing. Limits may differ between authenticated JSON mutations and public lead-capture submissions, but neither surface may accept an unbounded body.

## Health and readiness

`/health` reports only that the process can serve requests. It must not reveal filesystem paths, database names, environment values, versions of sensitive dependencies or tenant information.

`/ready` verifies the configured durable dependencies needed by this process. A failed dependency returns a generic unavailable result while detailed diagnostics remain in protected operator logs.

## Process model

The web process and monitoring worker remain separate bounded processes. The web application does not start an infinite worker thread. Deployment tooling is responsible for restart policy, scheduling, concurrency and log collection.

## Logging and secrets

Secrets, session credentials, invitation/reset tokens, SMTP passwords and authorization headers must never be logged. Identifiers may be logged only when operationally necessary and should not be combined with personal data unnecessarily.

## Explicit exclusions

- cloud-provider-specific infrastructure;
- Kubernetes or Terraform implementation;
- distributed rate limiting;
- billing and subscription enforcement;
- production SMTP-provider selection;
- penetration-test certification.

Related to issue #85.
