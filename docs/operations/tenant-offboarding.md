# Tenant offboarding

`veridra-tenant-offboard` is the operator boundary for permanently removing one Veridra tenant context. It is intentionally not exposed as a browser self-service delete button.

## Scope

The command removes tenant-owned state from:

- active/revoked sessions scoped to the selected tenant;
- tenant invitations;
- tenant memberships;
- the tenant identity row;
- global monitoring-job rows for that tenant;
- the complete durable tenant directory under `VERIDRA_TENANT_DATA_ROOT/<tenant_id>`.

It does **not** delete user accounts, password credentials, password-reset history or other user-level state. A Veridra user can belong to more than one tenant, so user/account erasure is a separate lifecycle operation.

## Mandatory recovery backup

Every offboarding operation requires a new `--backup-output`. Before any tenant state is mutated, Veridra creates a complete verified quiesced backup using the same backup contract as `veridra-backup`.

The backup contains the pre-offboarding identity database and complete tenant root. Keep it according to the organization's approved recovery/retention policy. Do not place it under the durable identity or tenant source directories.

If the backup cannot be created and validated, offboarding stops without mutation.

## Quiescence

The command requires `--confirm-quiesced`.

Before running it, stop or quiesce:

- `veridra-api` web writers;
- the monitoring worker/scheduler;
- billing reconciliation/webhook writers;
- any operator process that can modify the same identity or tenant stores.

The application cannot prove externally that every process is stopped. The flag is an operator assertion.

## Stripe/provider boundary

If the tenant has `workspace/billing/stripe.json`, offboarding refuses to proceed unless `--confirm-provider-billing-handled` is supplied.

That flag means the operator has already handled the external Stripe subscription/customer relationship as required, for example cancellation or transfer. The offboarding command does not call Stripe and does not claim that deleting local state cancels billing.

Do not use the confirmation flag merely to bypass the guard.

## Execution

Example:

```text
veridra-tenant-offboard \
  --tenant-id <24-hex-tenant-id> \
  --backup-output /secure/recovery/veridra-before-offboarding.zip \
  --confirm-quiesced
```

When a Stripe binding exists, add `--confirm-provider-billing-handled` only after provider-side handling is complete.

The identity and tenant paths default to `VERIDRA_IDENTITY_DB` and `VERIDRA_TENANT_DATA_ROOT`; they can also be supplied with `--identity-db` and `--tenant-data-root`.

## Cross-store safety

Veridra's tenant state spans an identity SQLite database, a global monitoring-job SQLite database and tenant filesystem state. Those stores do not share one transaction.

The command therefore:

1. validates the tenant and provider guard;
2. creates and verifies the full recovery backup;
3. stages the tenant directory under an inaccessible quarantine name;
4. captures and removes the tenant's monitoring rows;
5. deletes invitations, sessions, memberships and the tenant identity in one identity transaction;
6. removes the quarantined tenant directory only after database mutation succeeds.

If identity deletion fails after monitoring cleanup, Veridra attempts to restore the captured monitoring rows and staged tenant directory. If compensation is incomplete, the error explicitly directs the operator to recover from the verified backup.

If database removal succeeds but final filesystem erasure fails, the tenant is already unavailable to the application but a quarantined directory may remain. Treat that as a cleanup/privacy incident: keep writers stopped, locate and erase the `.offboarding-<tenant-id>-...` directory, then perform the post-checks below.

## Post-offboarding checks

Before resuming normal service:

- confirm the tenant ID no longer exists in `tenants`, `memberships`, `sessions` or `tenant_invitations`;
- confirm no `monitoring_jobs` rows remain for the tenant;
- confirm `VERIDRA_TENANT_DATA_ROOT/<tenant_id>` is absent;
- confirm any shared user can still access their other tenant memberships;
- run `veridra-ops-check`;
- start the web/worker processes and confirm `/health/ready` is healthy;
- retain the pre-offboarding backup only for the approved recovery/retention window.

## Not a complete data-subject erasure workflow

Tenant offboarding removes the workspace/customer context. It is not a claim that every item associated with every human user has been erased. Identity email delivery evidence and other operational/security records may also have independent retention requirements. User-level export/erasure should be implemented and governed separately so shared accounts and legitimate security/audit retention are handled correctly.
