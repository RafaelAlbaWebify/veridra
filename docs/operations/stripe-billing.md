# Stripe billing boundary

Veridra keeps subscription entitlements provider-neutral. Stripe is an adapter around `SubscriptionAuthority`; Stripe webhooks never write workspace plan files directly.

## Required configuration

Billing is disabled unless all of these are configured:

- `VERIDRA_STRIPE_SECRET_KEY`
- `VERIDRA_STRIPE_WEBHOOK_SECRET`
- `VERIDRA_STRIPE_PRICE_SOLO`
- `VERIDRA_STRIPE_PRICE_PROFESSIONAL`
- `VERIDRA_STRIPE_PRICE_AGENCY`
- `VERIDRA_TRUSTED_ORIGIN`

Do not commit live or test secrets. Configure the webhook endpoint in Stripe as `/api/billing/stripe/webhook` on the trusted HTTPS origin.

## Trust boundary

1. Checkout and Billing Portal requests require an authenticated tenant identity with `manage_tenant` capability.
2. Veridra creates hosted Stripe sessions server-side with the secret key. Price IDs come only from server configuration; the browser never supplies arbitrary Stripe prices.
3. Checkout stores the Veridra tenant identifier and requested plan in Stripe subscription metadata.
4. Webhooks are verified against the raw request body, `Stripe-Signature`, and the configured webhook secret before JSON is trusted.
5. For subscription create/update events, Veridra retrieves the current subscription from Stripe after verification instead of trusting webhook delivery order.
6. The Stripe Price ID is mapped back to a Veridra plan using server configuration. Unmapped prices cannot grant entitlements.
7. The resulting provider-neutral `SubscriptionUpdate` is applied through `SubscriptionAuthority`, retaining its replay, stale-state, evidence and rollback protections.
8. A subscription deletion suspends a workspace only when the deleted Stripe subscription is the subscription currently bound to that tenant.

## Customer binding

The tenant workspace stores only operational Stripe identifiers needed for reconciliation (`customer_id`, `subscription_id`) in `workspace/billing/stripe.json`. API keys and webhook secrets are never persisted there.

## Billing-cycle normalization

Veridra's quota ledger supports cycle anchor days 1–28 so every month has the anchor. Stripe billing-cycle days 29–31 are therefore normalized to day 28 for Veridra quota periods; Stripe remains authoritative for actual invoice dates.

## Operational checks before live billing

- Use Stripe test mode first.
- Confirm each configured Price is recurring and represents the intended Veridra plan.
- Exercise checkout, `customer.subscription.created`, plan change, payment-failure/suspension behavior, Billing Portal, cancellation, duplicate events and delayed/out-of-order events.
- Confirm reverse-proxy/application logs do not record secret keys, webhook secrets or full request bodies.
- Keep Stripe Dashboard access and webhook-secret rotation procedures under normal production secret-management controls.
