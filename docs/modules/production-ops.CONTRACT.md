# Production & Operations Contract
Responsibility: safe runtime configuration, health/readiness, deployment checks, access logging, backup/restore, ops checks and tenant offboarding.
Inputs: production environment/config, durable paths, trusted origin/hosts, SMTP/Stripe secrets, deployed HTTPS origin.
Outputs: fail-closed startup/preflight results, health signals, backup artifacts, restore/offboarding evidence, deployment acceptance result.
Guarantees: production-only hardening and hidden surfaces as documented; secret values not emitted by preflight.
Dependencies: host/edge/provider infrastructure supplied outside repo.
Failure behavior: missing/unsafe mandatory production configuration fails validation; deployment checker is read-only.
Constraints: current storage is single-writer; repo does not provision cloud/DNS/TLS/secret manager.
Non-responsibilities: choosing/provisioning vendor infrastructure automatically.