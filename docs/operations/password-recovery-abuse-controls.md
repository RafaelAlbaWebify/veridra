# Password-recovery abuse controls

Veridra applies a durable per-address throttle before issuing password-reset tokens or sending reset email.

## Application boundary

- Email addresses are normalized and represented in throttle state only by a SHA-256 subject hash.
- The default application allowance is three recovery requests per address in a 15-minute window.
- The next request enters a 15-minute lockout for that address.
- Throttle state is stored in the identity SQLite database and therefore survives process restarts.
- API and browser recovery use the same control.
- A throttled request does not issue a token and does not send email.
- Existing, missing and throttled addresses keep the same public recovery response. Do not expose lockout state or a `Retry-After` header from the recovery endpoint because that can weaken the account-enumeration boundary.

## Deployment boundary

The application-level throttle is deliberately keyed by recovery address rather than client IP. Production deployments should also apply bounded request-rate and connection controls at the trusted reverse proxy or edge to reduce distributed address spraying and high-volume requests against many addresses.

Do not trust arbitrary forwarded client-IP headers inside the application. Any IP-based edge policy belongs at infrastructure that has an authoritative connection identity.

## Operations

Repeated password-recovery activity can be investigated from protected infrastructure logs and identity-email delivery evidence, but logs must not contain reset tokens or SMTP credentials. Avoid logging raw request bodies for recovery endpoints.

The throttle is an abuse-control boundary, not an account-lock mechanism. Successful password reset continues to rely on possession of the one-time reset token and revokes existing sessions through the password-recovery service.
