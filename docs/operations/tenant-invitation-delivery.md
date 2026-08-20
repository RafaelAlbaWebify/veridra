# Tenant invitation delivery

Production tenant invitations use Veridra's configured transactional SMTP transport and browser acceptance flow.

## Owner workflow

- Team owners create or resend invitations from `/workspace/members`.
- When transactional email is configured, the bearer invitation token is not displayed to the owner. The recipient receives a secure acceptance link by email.
- Delivery success or failure is visible to the authenticated owner. A failed email does not consume the invitation; the owner can retry with Resend after SMTP is healthy.
- Development runtimes without SMTP retain a one-time manual-token fallback so local testing is not blocked.

## Recipient workflow

- New users open `/accept-invitation?token=...`, create their account and password, and are signed into the invited tenant after successful acceptance.
- Existing users must authenticate as the account matching the invitation email. The login continuation accepts only an internal `/accept-invitation` destination with a bounded token; arbitrary external or unrelated redirect targets are rejected.
- Existing-user acceptance adds the target-tenant membership and issues a session scoped to that tenant.
- Invitation services continue to enforce expiry, one-time consumption and active plan seat capacity atomically at acceptance.

## Token and evidence handling

Invitation tokens are bearer credentials. The invitation database and identity-email delivery evidence persist only token hashes/derived delivery keys, not the plaintext token. Acceptance pages send `Cache-Control: no-store` and `Referrer-Policy: no-referrer`.

Because the browser acceptance URL contains the token in its query string, reverse proxies, observability platforms and access logs must redact or omit query strings for `/accept-invitation`. Never record invitation URLs in analytics, error-report metadata, screenshots or support logs.

Identity-email delivery evidence records recipient, delivery status, subject, message digest and a one-way delivery key. SMTP failures are operational evidence, not a reason to expose the invitation token in a production response.

## Deployment expectations

- Use HTTPS at the trusted public origin.
- Configure and test SMTP before inviting production users.
- Protect identity-email evidence with the same filesystem and backup controls as password-reset delivery evidence.
- Alert on repeated invitation delivery failures.
- Keep raw invitation tokens, SMTP credentials and request query strings out of logs.
