# Workspace membership boundary

Veridra workspace members are local operational records used for seat limits, role planning, assignments and audit evidence.

They are not authenticated identities.

## Included

- Stable local member IDs.
- Validated email and display name.
- Role and active state.
- Plan-aware seat enforcement.
- Last-active-owner protection.
- Deterministic capability mapping.
- Append-only local operator audit events.

## Excluded

- Passwords or password reset.
- Login sessions.
- MFA or SSO.
- Identity verification.
- Request-level authorization as a member.
- Tenant isolation.
- Public deployment security.
- Proof that an audit actor corresponds to a real person.

An empty audit actor means an action originated from the unauthenticated local operator interface. It is operational evidence only.
