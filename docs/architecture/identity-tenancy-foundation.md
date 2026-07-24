# Identity and tenancy foundation

## Current boundary

Veridra 3.3.0 local workspace members are device-local operational records. They are not accounts, authenticated principals, sessions or tenant memberships.

This foundation introduces separate domain concepts for future production identity and tenancy work. It does not implement login, password handling, session persistence, email-delivery verification, invitations, recovery, MFA, SSO or public deployment security.

## Separate domain concepts

- `Tenant`: the customer or workspace security boundary.
- `AuthenticatedUser`: a global account identity independent of any tenant.
- `TenantMembership`: the explicit relation between one user and one tenant, including the tenant-specific role and active state.
- `AuthSession`: a provider-neutral server-side session record with issue, expiry and revocation state.
- `RequestIdentity`: a verified request context constructed only from current server-side records.
- `TenantObjectRef`: a tenant-qualified reference to a protected object.
- `TenantCapability`: the production-tenancy authorization vocabulary, separate from local workspace capabilities.

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

## Required request flow

1. Verify a credential, session cookie or token using a future authentication adapter.
2. Load the current session, user and tenant from durable server-side storage.
3. Resolve the tenant from an unambiguous trusted route, host or server-side session binding.
4. Load the user's active membership for that tenant.
5. Construct `RequestIdentity` from current verified server-side facts only.
6. Require every protected object lookup to include the tenant ID.
7. Reject mismatched tenant IDs before returning whether the object exists.
8. Apply `TenantCapability` authorization after tenant scope has been proven.

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

- Authentication provider selection and integration.
- Password hashing and credential storage.
- Session or token persistence.
- Secure cookie or token transport.
- Database schema and migrations.
- Request middleware.
- Tenant-qualified repositories for existing commercial records.
- Production authorization on existing routes.
- Invitation, recovery and email-verification delivery workflows.
- Billing enforcement.
- MFA, SSO and enterprise federation.

No production authentication or tenant-isolation claim is valid until those components are implemented and tested end to end.
