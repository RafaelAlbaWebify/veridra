# Production configuration preflight

Run the read-only preflight before starting a production Veridra runtime:

```text
veridra-production-preflight
```

The command validates production runtime, legal-link and SMTP configuration. Stripe is optional by default: if it is absent, the result is a warning because a Free-plan launch can still operate. For a paid launch, require Stripe explicitly:

```text
veridra-production-preflight --require-stripe
```

Exit codes follow the operational-check convention:

- `0` — required configuration is ready;
- `1` — ready with a warning, such as optional Stripe billing being absent;
- `2` — critical configuration failure; do not start the production runtime as configured.

Output is compact JSON containing only component names, statuses and generic messages. It does not emit configured paths, origins, legal URLs, SMTP credentials, Stripe keys, webhook secrets or Price IDs. The preflight is read-only: it does not create directories, contact SMTP or Stripe, resolve DNS, obtain TLS certificates or provision infrastructure.

A successful preflight proves configuration shape only. Deployment still requires provider-side resources such as compute, durable storage, DNS/TLS, SMTP account/domain setup, edge controls and—when paid launch is required—Stripe Products/Prices, Portal and webhook configuration. Run deployment-specific acceptance after those resources are connected.
