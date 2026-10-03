# Local-commercial H6 provider acceptance plan

Status: **COMPLETE — fresh local-commercial Stripe sandbox acceptance passed 2026-10-03**

## Purpose

H6 proves that the local commercial VERIDRA billing and optional SMTP boundaries work against real test providers without requiring an externally hosted VERIDRA server.

Repository unit/integration tests and historical operator Stripe mirror evidence are prerequisites, not substitutes for this acceptance.

## Evidence rules

Every phase must record:

- UTC start/finish timestamps;
- local VERIDRA origin used;
- tenant/workspace identifier;
- provider object identifiers needed for reconciliation;
- VERIDRA plan/status before and after;
- provider phase result;
- pass/fail and bounded error text;
- relevant artifact hashes when backup/restore is involved.

Evidence must not contain:

- Stripe secret keys;
- webhook signing secrets;
- SMTP passwords;
- login passwords;
- payment-card values;
- password-reset/invitation tokens;
- full webhook bodies when they contain unnecessary customer data.

## Phase 0 — configuration preflight

Run:

`python -m veridra.hosted_provider_preflight --output <evidence.json>`

Acceptance:

- Stripe secret key is test-mode;
- trusted origin is HTTPS **or** explicit loopback HTTP (`127.0.0.1` / `localhost`);
- Solo, Professional and Agency Price IDs resolve through Stripe;
- each Price is test-mode, active and recurring;
- optional SMTP configuration parses safely;
- evidence contains no secrets.

This phase contacts Stripe but does not create a customer/subscription or send email.

## Phase 1 — local commercial tenant and Checkout

Use a dedicated synthetic test tenant.

Acceptance:

1. local commercial signup/login works;
2. workspace begins at Free/active;
3. Billing page offers paid plans;
4. POST Checkout is same-origin protected;
5. Stripe-hosted Checkout session is created for the intended plan;
6. Checkout completes using Stripe test-mode payment data;
7. VERIDRA does **not** grant the plan merely because the browser returns from Checkout.

Evidence:

- tenant ID;
- Checkout Session ID if available without exposing secrets;
- selected plan;
- workspace state immediately after browser return.

Use `VERIDRA_COMMERCIAL_PROVIDER_SNAPSHOT.bat -TenantId <tenant-id>` before and after provider transitions. The snapshot is read-only and records workspace plan/status, Stripe customer/subscription binding and any checkout reservation without provider secrets.

## Phase 2 — verified webhook projection into loopback

Supported local command:

`VERIDRA_COMMERCIAL_STRIPE_LISTEN.bat`

This uses Stripe CLI `listen --forward-to` against `http://127.0.0.1:8011/api/billing/stripe/webhook`.

Acceptance:

1. Stripe CLI forwards a signed subscription event to the loopback webhook endpoint;
2. VERIDRA verifies the raw-body signature;
3. VERIDRA retrieves current subscription state from Stripe;
4. configured Price maps to one VERIDRA plan;
5. tenant metadata maps to the expected workspace;
6. workspace becomes the webhook-confirmed plan/status;
7. Stripe customer/subscription binding is persisted;
8. Checkout reservation is cleared.

No direct workspace-plan editing is allowed.

## Phase 3 — Portal and plan transitions

Acceptance:

- Billing page offers Stripe Billing Portal after binding;
- Portal session opens for the bound Stripe customer;
- a controlled plan upgrade projects through a verified Stripe event;
- a controlled downgrade projects through a verified Stripe event;
- plan limits/UX change only after webhook reconciliation.

Record provider and VERIDRA states for each transition.

## Phase 4 — payment failure and recovery

Acceptance:

- a Stripe test-mode `customer.subscription.updated` event whose authoritative current subscription status represents failed/unpaid collection projects to suspended VERIDRA state;
- suspended tenant cannot perform paid commercial mutations;
- billing/recovery path remains available;
- controlled provider recovery returns the workspace to active after verified reconciliation.

The exact Stripe test clock/card mechanism may vary; record the mechanism used. Invoice events are not VERIDRA's subscription authority and are not required by the listener.

## Phase 5 — cancellation

Acceptance:

- cancellation is performed through the supported Stripe management path;
- current bound subscription deletion/cancellation suspends the workspace;
- deletion for an obsolete subscription cannot suspend a replacement subscription;
- binding/evidence remain sufficient for reconciliation.

## Phase 6 — backup/restore/provider reconciliation

Acceptance:

1. capture an application backup containing the test tenant after provider binding;
2. restore it into an isolated local acceptance location;
3. do not expose the restored copy to production traffic;
4. compare restored workspace/binding with the authoritative Stripe test subscription;
5. use the isolated recovery-test tenant root printed by the recovery command and capture its restored state:

   `VERIDRA_COMMERCIAL_PROVIDER_SNAPSHOT.bat -TenantId <tenant-id> -TenantDataRoot "<recovery-test-root>\\tenants"`

6. run the reconciliation check read-only against that same isolated restored tenant root:

   `VERIDRA_COMMERCIAL_PROVIDER_RECONCILE.bat -TenantId <tenant-id> -TenantDataRoot "<recovery-test-root>\\tenants"`

7. if and only if drift is expected and reviewed, apply authoritative Stripe state explicitly to the isolated restored copy:

   `VERIDRA_COMMERCIAL_PROVIDER_RECONCILE.bat -TenantId <tenant-id> -TenantDataRoot "<recovery-test-root>\\tenants" -Apply`

8. prove that stale/replayed provider events cannot roll state backward.

The reconciliation command writes secret-free JSON evidence into Downloads. Read-only is the default; `-Apply` is required for mutation.

Record backup hash, restore location class (not credentials), subscription ID and final reconciled state.

## Optional SMTP phase

Only required if local commercial SMTP automation is enabled.

1. run the existing real SMTP transport check to a controlled mailbox;
2. verify visible sender/domain authentication at the provider/mailbox;
3. exercise at least one actual local commercial workflow (for example a lead notification);
4. confirm durable delivery evidence contains hashes/status but no SMTP credentials.

If SMTP remains disabled for launch, record it as disabled rather than fabricating delivery evidence.

## Fresh acceptance result — 2026-10-03

H6 completed against the actual local-commercial Windows runtime and Stripe sandbox.

Accepted phases:

- Phase 0: provider preflight passed with all three recurring test Prices active and the loopback origin trusted.
- Phases 1–2: Stripe-hosted Checkout completed; signed webhook projection bound the tenant and projected Free -> Solo.
- Phase 3: Billing Portal creation succeeded; Solo -> Professional -> Solo projected through real Stripe subscription updates and signed webhooks.
- Phase 4: a real failed sandbox recurring charge produced Stripe `past_due` and VERIDRA `suspended`; recovery returned both to active.
- Phase 5: current subscription cancellation produced `canceled` / suspended; a replacement Solo subscription became current and an obsolete deletion was handled but not applied.
- Phase 6: a quiesced verified backup was restored to an isolated location; initial provider reconciliation had no drift; intentional restored-copy drift was detected read-only, repaired only with explicit apply, replay was idempotent, and stale rollback was rejected.

The final Phase 6 evidence recorded a quiesced 15-file backup with SHA-256 `c95550e265bf24d2175f0769093ccdd3a7bfac2c9bb225392e669cf5ada94d24`, secret-free evidence, and a final restored state of Solo/active bound to the current Stripe replacement subscription.

H6 completion proves the local-commercial provider lifecycle. It does **not** by itself satisfy the broader first-customer release gate in issue #296, whose non-H6 legal/privacy and explicit-approval requirements remain separate.

## Completion rule

H6 is complete only when all required Stripe phases above have fresh local-runtime provider evidence.

Passing CI or the preflight alone is **not** H6 completion.

Historical operator/provider evidence may be linked as context but cannot be relabeled as local-commercial H6 acceptance.
