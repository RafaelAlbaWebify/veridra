# Production configuration preflight

Run the read-only preflight before starting a production Veridra runtime:

```text
veridra-production-preflight
```

The command validates production runtime, durable-storage topology, legal-link and SMTP configuration. Stripe is optional by default: if it is absent, the result is a warning because a Free-plan launch can still operate. For a paid launch, require Stripe explicitly:

```text
veridra-production-preflight --require-stripe
```

The storage check keeps production launch aligned with the verified backup/restore contract. The identity SQLite database and tenant-data root must be distinct rather than nested inside one another. Existing storage targets must have the expected file/directory shape and be readable/writable; for storage that has not been created yet, the nearest existing parent must permit creation. This prevents a deployment from passing configuration preflight with a durable layout that backup/restore later rejects.

Stripe validation uses the same webhook-secret overlap rules as production startup. During a controlled signing-secret rotation, `VERIDRA_STRIPE_WEBHOOK_SECRET_PREVIOUS` is accepted only when Stripe billing is otherwise configured, must contain a webhook signing secret, and must differ from the current `VERIDRA_STRIPE_WEBHOOK_SECRET`. A previous secret without active Stripe configuration, a malformed previous secret, or duplicate current/previous values is a critical preflight failure rather than a startup surprise.

Exit codes follow the operational-check convention:

- `0` — required configuration is ready;
- `1` — ready with a warning, such as optional Stripe billing being absent;
- `2` — critical configuration failure; do not start the production runtime as configured.

Output is compact JSON containing only component names, statuses and generic messages. It does not emit configured paths, origins, legal URLs, SMTP credentials, Stripe keys, webhook secrets or Price IDs. The preflight is read-only: it does not create directories, contact SMTP or Stripe, resolve DNS, obtain TLS certificates or provision infrastructure.

A successful preflight proves configuration shape and local durable-storage suitability only. Deployment still requires provider-side resources such as compute, durable volumes, DNS/TLS, SMTP account/domain setup, edge controls and—when paid launch is required—Stripe Products/Prices, Portal and webhook configuration. Run deployment-specific acceptance after those resources are connected.
