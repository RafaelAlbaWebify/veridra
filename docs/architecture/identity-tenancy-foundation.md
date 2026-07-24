# Identity and tenancy foundation

## Current boundary

Veridra 3.3.0 local workspace members are device-local operational records. They are not accounts, authenticated principals, sessions or tenant memberships.

This foundation introduces separate domain concepts for future production identity and tenancy work. It does not implement login, password handling, durable session persistence, email-delivery verification, invitations, recovery, MFA, SSO or public deployment security.

## Separate domain concepts

- `Tenant`: the customer or workspace security boundary.
- `AuthenticatedUser`: a global account identity independent of any tenant.
- `TenantMembership`: the explicit relation between one user and one tenant, including the tenant-specific role and active state.
- `AuthSession`: a provider-neutral server-side session record with issue, expiry and revocation state.
- `RequestIdentity`: a verified request context constructed only from current server-side records.
- `TenantObjectRef`: a tenant-qualified reference to a protected object.
- `TenantCapability`: the production-tenancy authorization vocabulary, separate from local workspace capabilities.
- `TrustedIdentityAdapter`: the provider-neutral interface responsible for resolving a verified request identity.

Local `WorkspaceMember` records are intentionally not reused for any of these types.

## Request identity construction

`build_request_identity` currently expresses the domain checks that an authentication adapter and persistence layer must satisfy. It rejects:

- pending or disabled accounts;
- accounts without a recorded email-verification time;
- suspended tenants;
- inactive or mismatched memberships;
- sessions belonging to another user;
- revoked sessions;
- expired sessions;
- sessions with an issue time in the future.

This function does not verify credentials, signatures, cookies or tokens. It accepts already-loaded records and therefore cannot be used as a production authentication mechanism by itself.

## Trusted middleware boundary

`VerifiedIdentityMiddleware` accepts a `TrustedIdentityAdapter`. The adapter may return either a typed `RequestIdentity` or no identity. The middleware binds only that typed result into server-side request state.

The middleware does not inspect identity headers, form values, query parameters or JSON fields. Tests prove that client-supplied user, tenant and role headers cannot create an authenticated request when the trusted adapter returns no identity.

The adapter interface is not an authentication provider. A production implementation must still verify secure credentials or session material, load current durable records, apply expiry and revocation, and call `build_request_identity` before returning an identity.

## Required request flow

1. Verify a credential, session cookie or token using a future authentication adapter.
2. Load the current session, user and tenant from durable server-side storage.
3. Resolve the tenant from an unambiguous trusted route, host or server-side session binding.
4. Load the user's active membership for that tenant.
5. Construct `RequestIdentity` from current verified server-side facts only.
6. Return that identity through `TrustedIdentityAdapter` and bind it in middleware.
7. Require every protected route to consume the bound identity dependency.
8. Require every protected object lookup to include the tenant ID.
9. Reject mismatched tenant IDs before returning whether the object exists.
10. Apply `TenantCapability` authorization after tenant scope has been proven.

Client-provided role, user ID or tenant ID values must never be trusted to construct a request identity.

## Tenant authorization policy

Tenant roles have an explicit capability map:

- owner and administrator: all tenant capabilities;
- analyst: projects, assessments, reports, monitoring, tasks and data viewing;
- sales: leads, reports and data viewing;
- viewer: data viewing only.

`require_tenant_capability` is a domain guard. Existing Veridra routes do not yet call it, so this branch does not claim production route authorization.

## Isolation invariant

Every protected commercial record must eventually carry a non-null tenant ID. Repository methods must accept tenant scope and query by both tenant ID and object ID. A lookup by object ID alone is not acceptable for protected records.

`TenantScopedRepository` makes identity and tenant-qualified references mandatory at the application boundary. `InMemoryTenantRepository` is a contract-test implementation only. It proves same-ID isolation, tenant-filtered listing, capability-gated mutation and non-disclosing cross-tenant rejection, but it is not durable storage or a substitute for database constraints.

## Migration boundary

Local JSON data has no authenticated owner or trustworthy tenant attribution. Migration must therefore be explicit:

- create a tenant through an authenticated administrative workflow;
- select a local data directory or export to import;
- show the operator exactly which records will be attached;
- require confirmation before attaching them to the tenant;
- record migration provenance and checksums;
- support rollback before deleting or rewriting local data;
- never infer an authenticated user from local member names or email addresses.

`TenantMigrationManifest` provides deterministic source fingerprints, per-record SHA-256 checksums, explicit target confirmation and planned/confirmed/applied/rolled-back states. It records migration intent and provenance only. It does not execute imports, database transactions or rollback.

## Threats that must be tested

- Direct-object-reference attempts using another tenant's object ID.
- Tenant ID substitution in route, form, query and JSON inputs.
- Identity spoofing through client-controlled headers.
- Disabled membership reuse from an otherwise valid session.
- Role changes while a session is active.
- Session fixation, replay, expiry and revocation.
- Invitation and account-recovery token disclosure or replay.
- Anonymous audit-tool access reaching protected tenant data.
- Error responses revealing whether another tenant's object exists.

## Still excluded

- Authentication provider selection and integration.
- Password hashing and credential storage.
- Durable session or token persistence.
- Secure cookie or token transport.
- A production `TrustedIdentityAdapter` implementation.
- Database schema and migrations.
- Tenant-qualified database implementations for existing commercial records.
- Authorization enforcement on existing routes.
- Transactional local-data import and rollback execution.
- Invitation, recovery and email-verification delivery workflows.
- Billing enforcement.
- MFA, SSO and enterprise federation.

No production authentication or tenant-isolation claim is valid until those components are implemented and tested end to end.
