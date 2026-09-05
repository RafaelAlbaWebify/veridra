# Webify client billing boundary

Status: **INTERNAL OPERATING ARCHITECTURE — IMPLEMENTED BOUNDARY; EXTERNAL STRIPE FLOW NOT VERIFIED**

Decision date: 2026-09-05

## Decision

Webify Presence Care customer billing and VERIDRA workspace/SaaS billing are separate concerns and must not share Stripe Price mappings.

For the first Webify customer:

- **Stripe is the external billing/payment/subscription authority for the Webify customer relationship.**
- **VERIDRA is an operational mirror/reference for that customer billing state.**
- Webify Presence Care Stripe resources are created and managed as Webify business billing resources, not as VERIDRA `free/solo/professional/agency` workspace plans.
- VERIDRA records provider invoice/payment references and the authoritative observed payment state through the agency recurring-service workflow.
- The existing VERIDRA Stripe workspace adapter stays disabled for the Webify internal/operator deployment unless VERIDRA itself is intentionally commercialized as a separate SaaS product later.

This preserves the previously frozen operating rule: if VERIDRA disagrees with Stripe/accounting evidence, Stripe/accounting evidence controls pending reconciliation.

## Why this distinction is required

The existing optional runtime Stripe adapter maps exactly three paid Stripe Price IDs to VERIDRA workspace entitlements:

- `solo`
- `professional`
- `agency`

Those plans govern VERIDRA workspace limits and features. They are not Webify Presence Care service tiers or country/currency prices.

The frozen Presence Care commercial model is instead:

- Ireland: activation €149 + €99/month;
- United Kingdom: activation £129 + £89/month;
- United States: activation $179 + $119/month;
- month-to-month initially;
- activation paid upfront;
- recurring service billed automatically in advance;
- larger remediation is separately approved/quoted.

Mapping any of those Presence Care Prices to `VERIDRA_STRIPE_PRICE_SOLO`, `VERIDRA_STRIPE_PRICE_PROFESSIONAL` or `VERIDRA_STRIPE_PRICE_AGENCY` would incorrectly make a customer service payment alter VERIDRA product entitlements.

## VERIDRA client-billing mirror

The agency recurring-service record already supports the required provider-neutral business mirror:

- recurring fee;
- ISO currency;
- billing cadence;
- next billing date;
- invoice reference;
- payment/provider reference;
- last payment state;
- `payment_blocked` lifecycle state;
- renewal/cancellation evidence.

The supported agency UI lets the operator record an invoice reference, payment state (`paid` or failed/overdue), provider reference and next billing date. This is the correct first-customer integration boundary.

Do not mark a service `paid` merely because an operator typed `paid`. The operator must first verify the authoritative Stripe/accounting evidence and record the corresponding provider/invoice reference.

## First-customer Stripe resource model

Create resources in **Stripe sandbox/test mode first**.

### Product

Use one clear business product family, e.g. `Webify Presence Care`.

### Recurring Prices

Create three monthly recurring Prices for the same bounded service offering, differentiated only by contract currency/market unless a later approved business rule changes the scope:

- EUR 99/month
- GBP 89/month
- USD 119/month

Record the exact Stripe Product/Price IDs in controlled provider evidence, not in public documentation. They are business-billing references and must not be assigned to VERIDRA workspace-plan environment variables.

### Activation fees

Activation is a one-time upfront business charge:

- EUR 149
- GBP 129
- USD 179

The initial sandbox flow may implement the activation amount as a one-time Price/invoice item or another Stripe Billing mechanism that produces an auditable invoice/payment record. The exact Stripe construction must be tested against invoice output and the actual tax/VAT decision before production approval.

### Customer / subscription

For the synthetic first-customer dry run:

1. create a synthetic Webify-controlled Stripe Customer;
2. create/select the correct recurring Presence Care Price for the intended test market;
3. collect the activation amount according to the tested invoice/payment design;
4. start the monthly recurring subscription;
5. ensure Stripe produces the expected invoice/payment evidence;
6. record Stripe invoice/payment/subscription references in VERIDRA through supported agency UI fields;
7. reconcile those references against the separate Webify sales/accounting record.

## Required Stripe sandbox scenarios

Before M3 can pass, exercise with actual Stripe sandbox objects rather than mocked IDs:

1. Initial activation payment succeeds.
2. Recurring subscription starts and first recurring invoice/payment succeeds.
3. Customer can access the configured Billing Portal or equivalent approved management path.
4. Recurring invoice is generated as expected.
5. Payment failure is simulated using Stripe's supported test methods.
6. Webify operator records the failed/overdue provider evidence in VERIDRA and transitions the service to the correct payment-blocked behavior.
7. Payment recovery succeeds and the authoritative Stripe state is mirrored back into VERIDRA.
8. Cancellation at the end of the prepaid period is exercised.
9. Stripe invoice output is reviewed against the current Irish/customer-jurisdiction invoice/tax requirements before any live customer use.
10. Stripe → bank/test settlement evidence where available → Webify sales/accounting record → VERIDRA reference chain is exercised and documented.

Stripe's current Billing documentation recommends sandbox testing of subscriptions, invoices, portal behavior and payment failures, and supports test clocks for advancing subscription lifecycle time. Use those provider-supported mechanisms rather than waiting for real calendar cycles.

## Runtime Stripe adapter rule

For the first Webify-operated VERIDRA deployment:

- leave `VERIDRA_STRIPE_SECRET_KEY`, `VERIDRA_STRIPE_WEBHOOK_SECRET`, `VERIDRA_STRIPE_PRICE_SOLO`, `VERIDRA_STRIPE_PRICE_PROFESSIONAL` and `VERIDRA_STRIPE_PRICE_AGENCY` **unset** unless a separate VERIDRA SaaS/workspace-billing launch is explicitly approved;
- do **not** run `veridra-production-preflight --require-stripe` merely because Webify Presence Care uses Stripe externally;
- standard `veridra-production-preflight` must still pass its runtime/storage/legal/SMTP gates; an unconfigured workspace Stripe adapter may remain a warning rather than a production failure for the Webify internal/operator deployment;
- M3 Stripe acceptance is evidenced separately by the real Stripe sandbox business-billing flow described in this document.

If VERIDRA is later sold as SaaS, that is a separate product decision requiring its own Prices, terms, billing acceptance and production gate.

## Production authority and reconciliation

Authority order for Presence Care billing:

1. Stripe provider state / generated billing evidence;
2. Webify statutory sales/accounting records;
3. VERIDRA operational mirror/reference.

If these disagree, do not silently overwrite evidence. Stop the affected billing/service transition, identify the authoritative provider/accounting event, reconcile the discrepancy, then update VERIDRA with the real reference/state.

## Security / data boundary

- Do not store card numbers or payment credentials in VERIDRA.
- Prefer Stripe-hosted payment/account-management surfaces.
- Do not put Stripe secret keys, webhook secrets or customer-sensitive billing data in Git, ordinary Docs, issues or chat.
- Store only provider references and bounded billing state needed by the operational workflow.
- Tax/VAT treatment must come from the actual transaction/customer/business status; do not infer it from geography alone.

## Readiness classification

- Boundary design: **IMPLEMENTED**.
- VERIDRA client billing mirror: **TESTED IN CI** through synthetic lifecycle tests.
- Real Stripe sandbox Presence Care resources: **NOT VERIFIED**.
- Real invoice/accounting reconciliation: **NOT VERIFIED**.
- Live customer billing: **NOT STARTED**.

**REAL OUTREACH COUNT = 0.**
