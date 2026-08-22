# Production onboarding boundary

The browser route `/onboarding` is a one-time local bootstrap helper. It is intentionally unavailable in production, including when the production identity database contains no users or tenants.

Production agency registration must use `/signup`. That path preserves the production customer-creation controls: email verification before activation, configured Terms acceptance, Privacy Notice presentation, durable legal-acceptance evidence and the normal signup abuse controls.

Do not expose or re-enable `/onboarding` at the reverse proxy as a production setup shortcut. A fresh production instance may use public `/signup` for its first customer once SMTP, legal URLs and durable storage are configured. Operator recovery/bootstrap workflows that intentionally bypass customer signup should use controlled CLI/restore procedures rather than a public browser route.

`veridra-deployment-check` verifies that a deployed production origin returns HTTP 404 from `/onboarding` while `/signup` remains available.
