# Durable Decisions

## D-001 — Evidence-first product boundary
Decision: use bounded public observations and explicit evidence; do not claim exhaustive SEO/security/AI visibility.
Reason: accuracy, safety and defensibility.
Status: active.

## D-002 — VERIDRA supports Webify; it is not the commercial identity
Decision: customers buy Webify service outcomes; VERIDRA is the agency/internal platform.
Status: **superseded by D-012** for the hosted product. This remains historically accurate for the operator-only phase and for `VERIDRA_ENV=operator`.

## D-003 — Conditional Presence Care after initial engagement
Decision: the initial assessment/improvement engagement can stand alone. Presence Care is offered only when recurring monitoring/care has evidence-backed value; its accepted service version must bound cadence, included work, escalation, exclusions and fee.
Reason: real-SMB validation #297 supported recurring value conditionally, not as a universal add-on.
Status: active; production pricing and customer-facing legal approval still pending. Canonical offer: `docs/product/webify-commercial-offer.md`.

## D-004 — Single-writer persistence initially
Decision: SQLite + filesystem state is acceptable for first deployment if operated single-writer.
Alternative: distributed/shared persistence now.
Reason: avoid premature infrastructure complexity.
Reconsider when concurrency/scale requires it.

## D-005 — Separate web and monitoring worker processes
Reason: monitoring durability and supervision boundaries.
Status: active production requirement.

## D-006 — Provider-neutral deployment
Decision: repository supplies container/runtime contracts but does not hardcode a cloud vendor, DNS, TLS, ingress or secret manager.
Status: active.

## D-007 — Stripe is payment/subscription authority; VERIDRA is not accounting ledger
Decision: external billing/invoice/payment evidence controls; VERIDRA stores references/mirrored operational state only.
Status: active.

## D-008 — No secrets/sensitive health data in ordinary workflow storage
Decision: use delegated/role/temp/password-manager access; no passwords/MFA/full card details/PHI in ordinary VERIDRA, Docs, GitHub or unapproved AI tools.
Status: active.

## D-009 — Production signup only; onboarding bootstrap non-production
Decision: `/signup` is public production registration; `/onboarding` must remain hidden in production.
Status: implemented/tested.

## D-010 — Synthetic lifecycle is not real-world readiness
Decision: #285–#289 engineering remains valid, but outreach is blocked by #284/#296 until deployment/providers/legal/dry-run/human gates pass.
Reason: prior readiness claim overreached synthetic evidence.
Status: active hard gate.

## D-011 — Initial market/vertical
Decision: English-speaking international markets; first controlled validation uses independent dental practices, starting with Ireland before wider expansion.
Status: business direction, not a code constraint.

## D-012 — Dual-runtime product architecture
Decision: preserve `VERIDRA_ENV=operator` as Webify's private loopback operator application while productizing `VERIDRA_ENV=production` as a hosted multi-tenant agency audit / white-label / lead-generation SaaS over the shared VERIDRA core.
Reason: the hosted commercial direction adopted at the end of VERIDRA 12 reuses substantial existing tenant, billing, reporting, lead-generation and monitoring capability without discarding the validated Webify operator workflow.
Initial hosted deployment boundary: single host/single durable volume with SQLite + tenant filesystem state, separate web/worker processes and off-host backups. Horizontal/multi-node deployment is deferred until shared transactional persistence is introduced.
Status: active. Hosted production still requires its own end-to-end acceptance, provider validation and commercial launch gate; operator #279/#284/#296 remain separate.
