# Signup legal links

Veridra does not ship operator-specific legal text. A production deployment must publish its own reviewed Terms of Service and Privacy Notice and configure their public HTTPS URLs.

Required production variables:

```text
VERIDRA_TERMS_URL=https://example.com/terms
VERIDRA_PRIVACY_URL=https://example.com/privacy
```

Both variables must be present together and must use HTTPS. Production startup fails closed when they are absent or invalid. Development and test runtimes may omit both.

## Signup behavior

When legal links are configured, `/signup`:

- links to the configured Privacy Notice at the point personal data are collected;
- requires a separate explicit Terms-of-Service checkbox before a verification email can be issued;
- does **not** describe the Privacy Notice itself as consent;
- records the exact Terms URL, Privacy URL, owner name/email and UTC acceptance timestamp in the identity SQLite database;
- stores only a SHA-256 hash of the signup verification token in legal evidence;
- gives pending, unverified legal evidence the same expiry as the signup verification token;
- opportunistically prunes expired, unactivated evidence during later legal-evidence activity;
- enriches activated evidence with tenant ID, user ID and activation time after email verification and retains that activated acceptance evidence;
- removes pending legal evidence immediately if SMTP delivery fails and the pending signup is cancelled.

The evidence table is `signup_legal_acceptances` and is part of the identity database, so it is included by the existing identity-database backup/restore contract. Expiry pruning is activity-driven rather than a guarantee that an abandoned row is physically deleted at the exact expiry second; a deployment may also invoke normal application activity or future maintenance tooling to trigger pruning.

Legacy evidence rows created before expiry tracking was introduced have no inferred expiry and are not deleted automatically because Veridra cannot safely reconstruct the historical token lifetime.

## Operator responsibility

The configured documents must be reviewed for the actual operator, jurisdiction, processing activities, subprocessors, retention, contact details, billing terms and other applicable obligations. Veridra validates only the link, acceptance, evidence and retention mechanics; it does not certify that the legal documents themselves are complete or legally sufficient.
