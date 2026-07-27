# Workspace policy migration boundary

Veridra's composed authenticated runtime uses tenant-qualified workspace configuration, usage evidence, quota enforcement and plan-change audit records.

## Authoritative tenant state

For an authenticated tenant, the authoritative files are stored below that tenant's data root:

```text
<tenant-root>/<tenant-id>/workspace/workspace.json
<tenant-root>/<tenant-id>/workspace/usage/*.json
<tenant-root>/<tenant-id>/workspace/plan-changes/*.json
```

The first-owner bootstrap creates a persisted Free workspace before committing the identity records. A failed bootstrap removes the workspace file and rolls back the identity transaction.

## Legacy process-global files

Older local versions may contain ambiguous files below the process-global workspace directory:

```text
<VERIDRA_DATA_DIR>/workspace/workspace.json
<VERIDRA_DATA_DIR>/workspace/usage/*.json
```

These files are **not** automatically migrated, copied, merged or attributed to any tenant. Their original tenant ownership cannot be proven from the file format, so automatic attachment would risk cross-tenant leakage or incorrect billing evidence.

The legacy helper functions retained in `workspace_web.py` are quarantined for standalone compatibility only. The composed runtime and supported tenant services must not import or call them.

An administrator may archive or delete the legacy directory after independently confirming it is no longer needed. A future explicit migration command would need a human-supplied tenant ID and a preview before any write; no implicit migration is permitted.

## Commercial-state limitation

Workspace plans remain local entitlement policy. They do not prove payment, create a subscription, charge a payment method, issue an invoice or synchronize with an external billing provider.
