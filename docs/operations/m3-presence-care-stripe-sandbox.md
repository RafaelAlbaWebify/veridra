# M3 Presence Care Stripe sandbox acceptance

Status: **ACTIVE / REAL PROVIDER EVIDENCE REQUIRED**

Date: 2026-09-26

## Purpose

Prove Webify Presence Care billing with real Stripe sandbox objects while keeping the
VERIDRA SaaS/workspace Stripe adapter disabled.

This is a business-billing test, not a VERIDRA SaaS billing test.

## Canonical first-market scenario

Use Ireland / EUR for the first acceptance exercise:

- product family: `Webify Presence Care`
- activation: EUR 149 one-time
- recurring service: EUR 99 monthly
- synthetic customer only
- Stripe sandbox/test mode only

Do not configure:

- `VERIDRA_STRIPE_SECRET_KEY`
- `VERIDRA_STRIPE_WEBHOOK_SECRET`
- `VERIDRA_STRIPE_PRICE_SOLO`
- `VERIDRA_STRIPE_PRICE_PROFESSIONAL`
- `VERIDRA_STRIPE_PRICE_AGENCY`

Those variables belong to the separate VERIDRA workspace/SaaS billing adapter.

## Evidence sequence

1. Create or select a Stripe sandbox.
2. Create a synthetic customer.
3. Create the `Webify Presence Care` product.
4. Create a EUR 149 one-time Price for activation.
5. Create a EUR 99/month recurring Price.
6. Exercise a successful activation payment/invoice in sandbox.
7. Start the recurring subscription and prove the first recurring invoice/payment.
8. Capture the non-secret Stripe references needed for reconciliation:
   - customer ID;
   - product/price references;
   - invoice reference;
   - payment reference;
   - subscription reference.
9. Mirror only the bounded invoice/payment/provider references and payment state into
   VERIDRA's recurring-service workflow.
10. Simulate payment failure using Stripe-supported sandbox methods.
11. Record failed/overdue state in VERIDRA and confirm the service becomes
    `payment_blocked`.
12. Simulate payment recovery and mirror the authoritative Stripe state back into VERIDRA.
13. Exercise cancellation at period end.
14. Record the corresponding accounting-system reference separately and reconcile:
    Stripe -> accounting record -> VERIDRA operational reference.

## Acceptance

M3 Stripe/accounting evidence is not complete merely because objects exist.

Acceptance requires:

- real sandbox objects;
- successful activation and recurring payment evidence;
- failed-payment and recovery evidence;
- cancellation evidence;
- bounded references mirrored into VERIDRA through supported UI;
- accounting system-of-record reference;
- no secrets/card data copied into repository, chat, issues or VERIDRA.

## Safety

Use only Stripe test/sandbox payment details. Never use real card details in test mode.
