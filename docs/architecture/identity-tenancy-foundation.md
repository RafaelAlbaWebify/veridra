# Identity and tenancy foundation

## Purpose

Veridra local `WorkspaceMember` records remain device-local operational metadata. They are not accounts, authenticated principals, sessions or tenant memberships.

This foundation introduces a separate production identity and tenant boundary with durable server-side records, cookie-backed sessions, capability authorization and tenant-qualified commercial storage. It is a foundation for a hosted multi-tenant product, not a claim that every legacy route or deployment concern is complete.

## Authentication approach

The implemented primary authentication path is local email, tenant slug and password authentication backed by SQLite:

- passwords use scrypt with a random salt;
- login returns a cryptographically random opaque session credential;
- only the SHA-256 credential hash is stored;
- the secure cookie is `HttpOnly`, `Secure`, `SameSite=Strict` and scoped to `/`;
- every request resolves the current session, user, tenant and membership from server-side records;
- client-provided user IDs, tenant IDs, roles, authorization headers, form fields and JSON claims cannot construct an identity;
- disabled users, unverified emails, suspended tenants, inactive memberships, revoked sessions and expired sessions fail closed.

The domain remains provider-neutral enough for a later OAuth/OIDC adapter, but OAuth/OIDC, MFA, SSO and federation are not implemented in this PR.

## Domain concepts

- `Tenant`: customer security boundary.
- `AuthenticatedUser`: global account identity independent of tenant membership.
- `TenantMembership`: explicit user-to-tenant relation with tenant-specific role and active state.
- `AuthSession`: server-side issue, expiry and revocation record.
- `RequestIdentity`: verified request context built only from current server-side records.
- `TenantObjectRef`: tenant-qualified protected-object reference.
- `TenantCapability`: authorization vocabulary independent of local workspace capabilities.
- `TrustedIdentityAdapter`: interface that resolves a verified request identity.

## Request identity flow

1. Read the bounded opaque credential only from the secure session cookie.
2. Hash the credential and load the current session record.
3. Join the session to the current user, tenant and exact membership.
4. reject inactive, suspended, revoked, expired, future-issued or mismatched records.
5. construct `RequestIdentity` from those current server-side facts.
6. bind only that typed identity into request state.
7. require protected routes to consume the identity or capability dependency.
8. tenant-qualify protected lookups before disclosing whether an object exists.

The selected tenant is bound into the server-side session. It is never selected from a browser-supplied tenant claim during request authorization.

## Authorization policy

- owner and administrator: all tenant capabilities;
- analyst: projects, assessments, reports, monitoring, tasks and data viewing;
- sales: leads, reports and data viewing;
- viewer: data viewing only.

Protected tenant APIs enforce this capability map. Cross-tenant object references are rejected before lookup or represented as the same `404` boundary as a missing object.

## Session lifecycle

Implemented and tested:

- session issue after trusted password authentication;
- current-session inspection;
- atomic rotation with current-session revocation in the same SQLite transaction;
- logout and cookie clearing;
- account-wide revocation after password change or password reset;
- session inventory across tenant contexts;
- selective revocation of another session owned by the same user;
- replay, expiry and revocation rejection.

The current session must be ended through logout rather than the inventory-revocation endpoint.

## Invitation, recovery and verification boundaries

New-account invitations use hashed, expiring, single-use tokens and atomically create the account, password credential and target membership.

Existing-account invitations require an authenticated active and verified account whose database email exactly matches the invitation. Acceptance creates only the new target membership and consumes the token atomically.

Password recovery uses generic request semantics, a trusted delivery-adapter boundary, hashed expiring single-use reset tokens and account-wide session revocation after reset.

Invitation acceptance currently records the invited email as verified because possession of the single-use invitation token is the account-verification ceremony. A separate independent email-verification workflow for other onboarding paths is not implemented.

## Durable identity schema and migrations

SQLite stores tenants, users, memberships, password credentials, sessions, invitations, password-recovery records and login-throttle records.

A versioned migration registry now applies identity migrations transactionally during configured startup. Migration version 1 normalizes stored emails and creates normalized uniqueness. A legacy normalized-email collision fails atomically instead of silently merging accounts.

SQLite is the current durable implementation, not a claim that it is the final production database.

## Tenant-qualified commercial records

Authenticated tenant-qualified storage and APIs now cover:

- projects and monitoring configuration;
- leads and public lead capture for server-bound forms;
- lead forms and form-to-tenant bindings;
- webhook and email delivery attempts for bound capture;
- remediation tasks;
- report profiles;
- project assessment history and comparison;
- tenant-derived HTML, PDF and evidence-ZIP report generation;
- manual monitoring execution and tenant-local monitoring email attempts.

Tenant-bound public forms resolve their tenant only from the durable server-side binding. Existing pre-binding legacy forms retain an explicit compatibility fallback; unbound forms remain on the legacy public path.

Legacy administrative pages and flat stores are not all converted or removed by this PR.

## Local-data migration boundary

Local JSON records do not contain trustworthy authenticated ownership. The offline operator migration flow therefore requires:

- deterministic source inventory and checksums;
- explicit destination tenant confirmation;
- apply-time rejection of added, removed or modified source JSON;
- target-ID and destination-checksum verification;
- safe identical-target reuse and conflicting-target rejection;
- rollback evidence and refusal to delete changed targets.

No real customer data is migrated automatically and local member names or emails are never promoted into authenticated identities.

## Threats covered by tests

- identity spoofing through headers, form values or JSON claims;
- direct-object-reference and tenant-substitution attempts;
- disabled users, memberships and tenants;
- session fixation, replay, rotation, expiry and revocation;
- password and recovery-token misuse;
- invitation expiry, replay, account mismatch and concurrent consumption;
- same-ID tenant isolation;
- anonymous access to protected tenant APIs;
- migration-source drift and rollback tampering.

## Security and operational exclusions

The following remain outside the proven production boundary:

- explicit Origin/Referer or synchronizer-token protection for authenticated browser mutation requests; `SameSite=Strict` is present but is not the complete documented CSRF strategy;
- trusted reverse-proxy and forwarded-header configuration;
- distributed/IP-based throttling at the deployment edge;
- production SMTP or transactional-email provider configuration and delivery monitoring;
- independent email verification for onboarding paths not based on an invitation token;
- OAuth/OIDC, MFA, SSO and enterprise federation;
- deployment secret management and rotation;
- a comprehensive immutable production audit log;
- complete conversion or retirement of legacy administrative routes;
- migration against actual customer data;
- broad external penetration testing;
- billing and subscription enforcement;
- durable background scheduling and worker execution.

No claim that Veridra is a complete production SaaS should be inferred from this foundation PR.