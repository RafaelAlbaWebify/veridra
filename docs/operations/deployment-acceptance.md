# Deployment acceptance check

After provisioning a real Veridra host, run the provider-neutral remote deployment gate against its public HTTPS origin:

```text
veridra-deployment-check --origin https://app.example.com
```

The command is intentionally read-only. It validates that the supplied value is a bare public HTTPS origin, resolves the hostname to public addresses, pins the connection to the validated address while preserving the original TLS SNI/Host identity, and then checks:

- `/health/live` returns HTTP 200 with `{"status":"ok"}`;
- `/health/ready` returns HTTP 200 with `{"status":"ok"}`;
- `/signup` exposes the expected public agency-signup surface;
- `/onboarding` returns HTTP 404, confirming the one-time local bootstrap form is not exposed in production;
- `/openapi.json` returns HTTP 404, confirming the production API schema and interactive documentation are not publicly exposed;
- production HSTS, anti-sniffing, anti-framing and CSP headers are present on the public application surface;
- liveness, readiness and signup responses carry `Cache-Control: no-store`.

The production runtime hides `/onboarding` even when the identity database is completely empty. Production customer/owner registration must use `/signup`, preserving email verification and configured legal-acceptance evidence. The one-time `/onboarding` browser bootstrap remains available only in development/test-style runtimes for local setup.

The production runtime also hides `/openapi.json`, `/docs`, `/docs/...` and `/redoc` at the runtime boundary. Development and test runtimes retain FastAPI's interactive documentation for local engineering use.

The command does not create accounts, submit forms, mutate tenant state, contact Stripe/SMTP, or print the tested origin/IP in its JSON result. Exit code `0` means the checked deployment contract passed; exit code `2` means at least one critical deployment check failed.

This is a deployment smoke/security gate, not a replacement for the full browser commercial acceptance journey or an independent security assessment. After a real environment is connected, use it after `veridra-production-preflight` and before end-to-end signup/billing acceptance.
