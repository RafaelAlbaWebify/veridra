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

An optional rotation-overlap setting is supported:

- `VERIDRA_STRIPE_WEBHOOK_SECRET_PREVIOUS`

It is valid only while Stripe billing is otherwise configured, must contain a distinct `whsec_...` value, and should be removed after the old Stripe signing secret has expired.

## Trust boundary

1. Checkout and Billing Portal requests require an authenticated tenant identity with `manage_tenant` capability.
2. Veridra creates hosted Stripe sessions server-side with the secret key. Price IDs come only from server configuration; the browser never supplies arbitrary Stripe prices.
3. Checkout stores the Veridra tenant identifier and requested plan in Stripe subscription metadata.
4. Webhooks are verified against the raw request body and `Stripe-Signature` before JSON is trusted. During an explicit signing-secret rotation overlap, either the current or configured previous endpoint signing secret may verify the delivery.
5. For subscription create/update events, Veridra retrieves the current subscription from Stripe after verification instead of trusting webhook delivery order.
6. The Stripe Price ID is mapped back to a Veridra plan using server configuration. Unmapped prices cannot grant entitlements.
7. The resulting provider-neutral `SubscriptionUpdate` is applied through `SubscriptionAuthority`, retaining its replay, stale-state, evidence and rollback protections.
8. A subscription deletion suspends a workspace only when the deleted Stripe subscription is the subscription currently bound to that tenant.

## Customer binding

The tenant workspace stores only operational Stripe identifiers needed for reconciliation (`customer_id`, `subscription_id`) in `workspace/billing/stripe.json`. API keys and webhook secrets are never persisted there.

## Billing-cycle normalization

Veridra's quota ledger supports cycle anchor days 1–28 so every month has the anchor. Stripe billing-cycle days 29–31 are therefore normalized to day 28 for Veridra quota periods; Stripe remains authoritative for actual invoice dates.

## Webhook signing-secret rotation

Stripe can keep the old endpoint signing secret active temporarily while a new secret is introduced. Use that overlap rather than creating a verification outage.

A controlled rotation is:

1. In Stripe, start a webhook endpoint signing-secret roll with delayed expiry for the old secret.
2. Put the newly generated secret into `VERIDRA_STRIPE_WEBHOOK_SECRET`.
3. Put the still-active old secret into `VERIDRA_STRIPE_WEBHOOK_SECRET_PREVIOUS`.
4. Deploy/restart Veridra and verify that webhook deliveries continue to return successful responses.
5. Exercise a controlled Stripe test-mode event and confirm normal entitlement reconciliation.
6. After Stripe expires the old secret, remove `VERIDRA_STRIPE_WEBHOOK_SECRET_PREVIOUS` and deploy/restart again.

Do not leave the previous secret configured indefinitely. If a signing secret is believed compromised, do not use a long overlap merely to avoid a restart; rotate according to the incident response and Stripe-side expiration policy.

`VERIDRA_STRIPE_WEBHOOK_SECRET_PREVIOUS` is only for endpoint signing-secret rotation. It is not a second Stripe API key and is never used to authenticate Checkout, Portal or subscription retrieval calls.

## API-key rotation

`VERIDRA_STRIPE_SECRET_KEY` remains a single current server-side Stripe API credential. Rotate it through the external secret store and a controlled deployment/restart, then expire the old key in Stripe after the new deployment has been validated. Do not store old API keys in tenant state or add them as webhook fallback secrets.

## Operational checks before live billing

- Use Stripe test mode first.
- Confirm each configured Price is recurring and represents the intended Veridra plan.
- Exercise checkout, `customer.subscription.created`, plan change, payment-failure/suspension behavior, Billing Portal, cancellation, duplicate events and delayed/out-of-order events.
- Confirm reverse-proxy/application logs do not record secret keys, webhook secrets or full request bodies.
- Practice webhook signing-secret rotation before production launch.
- Keep Stripe Dashboard access and secret rotation procedures under normal production secret-management controls.

## Scope of this adapter

This code establishes the authenticated Stripe boundary and entitlement reconciliation path. It does not create a Stripe account, products, Prices, Portal configuration or a live provider webhook endpoint on the operator's behalf. Those provider-side resources must be configured explicitly and validated in Stripe test mode before any live charge is possible.
