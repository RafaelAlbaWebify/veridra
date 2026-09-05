# Identity & Billing Contract
Responsibility: signup/verification/login/recovery/invitations/memberships/roles/entitlements and provider-neutral subscription state with Stripe adapter.
Inputs: browser/API identity actions; signed provider events; configured SMTP/Stripe settings.
Outputs: authenticated sessions, membership/tenant state, entitlement state, external billing references.
Guarantees: production signup path, non-enumerating recovery/signup behavior where implemented, signed webhook verification, replay/order protection.
Dependencies: identity SQLite, SMTP, optional Stripe.
Failure behavior: production config fails closed when mandatory settings missing; provider disagreement must not be overwritten by invented local state.
Constraints: VERIDRA is not accounting ledger; no full card storage.
Non-responsibilities: VAT/tax determination, provider provisioning, company books.