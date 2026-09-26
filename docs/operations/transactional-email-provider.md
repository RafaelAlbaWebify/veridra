# Transactional email provider decision

Status: **OPTIONAL AUTOMATION / NOT A FIRST-CUSTOMER GATE**

Decision date: 2026-09-05

## Decision

Brevo is the preferred SMTP / transactional email option if Webify chooses to automate report or monitoring-message delivery. It is not required for VERIDRA's first-customer readiness under the canonical operator-local architecture.

This is a provider-selection decision only. It does **not** mean that a Webify Brevo account, sender, domain authentication, SMTP credentials, DPA posture, retention settings or production delivery have been externally verified or production approved.

## Why Brevo is the first choice

VERIDRA contains SMTP-capable flows for report delivery, monitoring summaries and historical SaaS identity workflows. Under the canonical operator-local model, customers do not access VERIDRA directly, so signup verification, tenant invitations and customer password-reset delivery are not required for the first customer. The first-customer workload is expected to be low volume.

Current official Brevo material reviewed on 2026-09-05 states:

- SMTP relay is supported for applications that can send through SMTP;
- the Free plan includes 300 email sends per day and transactional email;
- Brevo's transactional-email product page states data hosting in France and Germany on EU-based servers;
- Brevo states ISO 27001 certification and GDPR support on that product page;
- Brevo publishes a Data Processing Agreement as part of its Terms of Service.

These characteristics fit the first VERIDRA deployment better than paying immediately for a higher-volume provider and reduce the data-location/transfer complexity of alternatives whose primary account/message metadata is stored in the United States.

Price/free-tier availability is not a production criterion by itself. Re-check the actual plan, limits and commercial terms immediately before account activation.

## Intended scope

Brevo may be used for:

- automated PDF report delivery;
- automated monitoring summaries;
- other bounded operational/customer transactional messages if Webify later chooses to automate them.

Historical SaaS identity flows (signup verification, tenant invitation and customer password reset) remain implemented but are outside the first-customer gate while VERIDRA is operator-local.

Potential data processed includes recipient name/email, subject/body, delivery metadata and short-lived security links/tokens contained in transactional messages.

The following must not be deliberately sent through ordinary transactional email unless a separately approved workflow explicitly requires it:

- passwords or MFA/recovery secrets;
- payment-card data;
- PHI/clinical records;
- unnecessary customer confidential data;
- bulk customer databases unrelated to the delivery purpose.

VERIDRA durable delivery evidence must continue to avoid retaining sensitive token values.

## Production configuration boundary

Before this provider can become **PRODUCTION APPROVED**, complete and retain evidence for all of the following:

1. Create the exact Webify Brevo account and record the legal/account owner.
2. Review the then-current Terms of Service and DPA for the exact service/account being used.
3. Review Brevo's current subprocessor list, processing/hosting regions and international-transfer position.
4. Confirm account security, administrator access and MFA options.
5. Select the exact sender identity/domain or subdomain.
6. Configure and verify every DNS authentication record required by Brevo for that sender, including DKIM/SPF and DMARC posture as applicable to the chosen setup.
7. Create SMTP credentials locally in the operator/provider environment. Never commit credentials to Git or paste them into chat/docs/issues.
8. Configure VERIDRA production variables using the real provider values:
   - `VERIDRA_SMTP_HOST`
   - `VERIDRA_SMTP_PORT`
   - `VERIDRA_SMTP_ENCRYPTION`
   - `VERIDRA_SMTP_SENDER`
   - `VERIDRA_SMTP_SENDER_NAME`
   - `VERIDRA_SMTP_USERNAME` when required
   - `VERIDRA_SMTP_PASSWORD` through the production secret boundary
9. Confirm provider log/message retention settings and minimize retention consistent with operational/security needs.
10. Confirm bounce/complaint handling and incident/support path.
11. Run VERIDRA production preflight against the actual configuration.
12. If SMTP automation is enabled, prove real delivery to a controlled mailbox for the exact enabled business workflow, such as report delivery or monitoring summary.
13. Confirm that delivered messages contain no unnecessary sensitive data and that delivery evidence excludes credentials or sensitive tokens.
14. Record delivery evidence without copying credentials or sensitive token values into the evidence pack.
15. Update the Webify Subprocessor Register with verification date, owner and final production status.

## Acceptance states

### IMPLEMENTED
Provider choice and application configuration boundary documented.

### TESTED IN CI
Repository SMTP behavior remains covered by VERIDRA tests. This does not test Brevo infrastructure.

### DEPLOYED
Real Brevo SMTP settings are installed on the real VERIDRA host through the production secret/configuration boundary.

### EXTERNALLY VERIFIED
If SMTP automation is enabled, the exact approved operator workflow (for example report delivery) is successfully delivered through the real Brevo account with sender/domain authentication and evidence reviewed.

### PRODUCTION APPROVED
External verification passes and Webify's DPA/subprocessor/security/retention/account configuration review is complete.

## Rollback / replacement

Brevo is not an application-architecture lock-in. VERIDRA uses a provider-neutral SMTP boundary. If Brevo fails legal/privacy/security/deliverability/economic validation, select another SMTP provider, update the Subprocessor Register, reconfigure the environment, and repeat the full external verification gate.

## First-customer gate

SMTP/Brevo automation is optional. Manual operator-mediated email delivery is acceptable for the first customer. Enabling SMTP grants no operability credit by itself; credit requires real delivery evidence for a workflow that Webify actually intends to use.

**REAL OUTREACH COUNT = 0.**
