# Tenant-qualified lead delivery attempts

Webhook and email delivery-attempt records created by a tenant-bound public lead form are stored beneath the bound tenant data root:

- `tenants/<tenant_id>/lead-deliveries`
- `tenants/<tenant_id>/email-deliveries`

The tenant identifier is resolved only from the server-side lead-form binding. Public requests cannot provide or override it.

Unbound legacy forms retain the original global attempt stores for compatibility.

Authenticated readers may inspect attempts through `GET /api/tenant/leads/{lead_id}/delivery-attempts`. The endpoint verifies the lead inside the current request tenant before reading attempt records. Missing, cross-tenant, and orphan attempt histories return the same lead-not-found boundary.

This change does not migrate or delete historical global delivery-attempt records automatically.
