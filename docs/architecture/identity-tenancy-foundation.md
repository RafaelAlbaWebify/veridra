# Identity and tenancy foundation

## Current boundary

Veridra 3.3.0 local workspace members are device-local operational records. They are not accounts, authenticated principals, sessions or tenant memberships.

This foundation introduces separate domain concepts for future production identity and tenancy work. It does not implement login, password handling, session persistence, email verification, invitations, recovery, MFA, SSO or public deployment security.

## Separate domain concepts

- `Tenant`: the customer or workspace security boundary.
- `AuthenticatedUser`: a global account identity independent of any tenant.
- `TenantMembership`: the explicit relation between one user and one tenant, including the tenant-specific role and active state.
- `RequestIdentity`: the authenticated request context that must be constructed only after session or token verification.
- `TenantObjectRef`: a tenant-qualified reference to a protected object.

Local `WorkspaceMember` records are intentionally not reused for any of these types.

## Required request flow

1. Verify a session or token using a future authentication adapter.
2. Load the current user and reject pending, disabled or unverified accounts according to the selected policy.
3. Resolve the tenant from an unambiguous trusted route, host or server-side session binding.
4. Load the user's active membership for that tenant.
5. Construct `RequestIdentity` from verified server-side facts only.
6. Require every protected object lookup to include the tenant ID.
7. Reject mismatched tenant IDs before returning whether the object exists.
8. Apply capability authorization after tenant scope has been proven.

Client-provided role, user ID or tenant ID values must never be trusted to construct a request identity.

## Isolation invariant

Every protected commercial record must eventually carry a non-null tenant ID. Repository methods must accept tenant scope and query by both tenant ID and object ID. A lookup by object ID alone is not acceptable for protected records.

The current `require_tenant_scope` guard is a domain-level invariant and test fixture. It is not a replacement for tenant-qualified database queries.

## Migration boundary

Local JSON data has no authenticated owner or trustworthy tenant attribution. Migration must therefore be explicit:

- create a tenant through an authenticated administrative workflow;
- select a local data directory or export to import;
- show the operator exactly which records will be attached;
- require confirmation before attaching them to the tenant;
- record migration provenance and checksums;
- support rollback before deleting or rewriting local data;
- never infer an authenticated user from local member names or email addresses.

## Threats that must be tested

- Direct-object-reference attempts using another tenant's object ID.
- Tenant ID substitution in route, form, query and JSON inputs.
- Disabled membership reuse from an otherwise valid session.
- Role changes while a session is active.
- Session fixation, replay, expiry and revocation.
- Invitation and account-recovery token disclosure or replay.
- Anonymous audit-tool access reaching protected tenant data.
- Error responses revealing whether another tenant's object exists.

## Still excluded

- Authentication provider selection.
- Password hashing and credential storage.
- Session or token persistence.
- Database schema and migrations.
- Request middleware.
- Production authorization on existing routes.
- Billing enforcement.
- MFA, SSO and enterprise federation.

No production authentication or tenant-isolation claim is valid until those components are implemented and tested end to end.
