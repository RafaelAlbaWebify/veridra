# Hosted H5 lead-generation product acceptance

Status: **COMPLETE**
Closed: 2026-10-02

## Scope

H5 completes the hosted lead-generation surface without introducing a second branding or CRM persistence model.

## Closure baseline

- final H5 head: `bf176450`;
- GitHub Actions run: `37006643458`;
- result: **success**;
- Ruff: passed;
- strict mypy: passed;
- pytest: passed;
- deterministic audit: passed;
- discovery acceptance: passed;
- Windows portability: passed;
- sales-contract Playwright: passed;
- full operator Playwright acceptance: passed.

## Acceptance matrix

| H5 criterion | Evidence | Result |
| --- | --- | --- |
| Embed setup UX | tenant form Setup page exposes production URL, iframe snippet, parent-origin guidance and verification checklist | PASS |
| Form branding | tenant-bound public forms reuse the selected tenant Report Profile organisation, accent colour and validated embedded logo | PASS |
| No duplicate branding model | branding is resolved from existing `ReportProfile`; `LeadFormConfig` retains only `profile_id` | PASS |
| Deleted profile recovery | missing/deleted selected profile falls back to form label/default colour instead of breaking public capture | PASS |
| Tenant isolation | public profile lookup is qualified by the form binding tenant; a profile present only in another tenant cannot brand the form | PASS |
| Plan/upgrade guidance | downgraded workspaces keep inventory/deletion recovery while create/edit/public capture remain entitlement-guarded | PASS |
| Origin behavior | allowed parent origin can load embed; trusted Veridra origin can post back; unrelated origins remain blocked | PASS |
| Proxy-aware throttling | public rate limiting uses the controlled internal client-IP header only in production and falls back safely | PASS |
| Lead pipeline ergonomics | inbox/detail expose source form, submitted time, qualification/follow-up state and recover after source-form deletion | PASS |
| Project conversion | conversion is project-native, capacity-aware and idempotent | PASS |
| Assessment attribution | tenant-scoped captured assessment ID is preserved into project history | PASS |
| Report attribution | lead-form Report Profile is carried into the converted client project | PASS |
| Completion CTA | configured validated CTA appears only after successful capture/assessment | PASS |

## Branding boundary

The public form does not copy logo/colour fields into `LeadFormConfig`.

When a bound form selects a report profile:

- organisation label comes from the tenant profile;
- accent colour comes from the tenant profile;
- the validated embedded PNG/JPEG logo is rendered under the existing CSP (`img-src data:`);
- the same branding is retained on the assessment-complete response.

If the profile is unavailable, the form remains operational using its own organisation label and the default Veridra accent.

## Preserved security/commercial guards

H5 does not weaken:

- tenant binding;
- explicit consent;
- usage reservations/metering;
- embedded-form plan entitlement;
- origin allow-list behavior;
- public throttling;
- same-origin form actions;
- CSP/script restrictions;
- project-capacity enforcement.

## What H5 does not prove

H5 does not prove:

- real hosted SMTP delivery;
- real Stripe Checkout/webhook lifecycle;
- real public reverse-proxy rate-limit behavior on the eventual host;
- hosted human usability on the actual production stack.

Those remain H6/H7.

## Next phase

**H6 — Paid hosted provider acceptance**

Required provider evidence:

- Stripe test-mode Checkout;
- verified hosted webhook projection;
- upgrade/downgrade;
- payment-failure/suspension;
- Billing Portal;
- cancellation;
- reconciliation after backup/restore;
- real SMTP sender/delivery if SMTP automation is enabled.

Historical operator Stripe mirror evidence remains useful context but does not satisfy hosted H6 by itself.
