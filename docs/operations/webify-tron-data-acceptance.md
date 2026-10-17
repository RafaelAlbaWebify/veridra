# Webify / VERIDRA — non-destructive TRON data acceptance

Status (2026-10-16): **backup/recovery and restored-data application smoke passed on TRON**.
The complete prospect-to-delivery workflow remains unverified on the real workstation.
Green CI proves synthetic compatibility, not full workstation operability.

## One-command acceptance (recommended)

From the checked-out `refactor/webify-operator-only` branch, in PowerShell:

```powershell
& .\\scripts\\windows\\veridra-commercial-local.ps1 data-audit
```

This action quiesces the managed Webify services for a consistent backup,
restarts them afterward, restores the latest snapshot to an isolated directory,
and writes a counts-only report to
`%LOCALAPPDATA%\\VeridraCommercial\\audits\\WEBIFY_DATA_AUDIT_*.json`.
It is **not** zero-interruption: backup briefly stops managed services.
Only share the JSON report; do not upload the actual backup or customer data.

## Safety boundary

1. Keep the currently functioning installation and `main` untouched.
2. From the `refactor/webify-operator-only` checkout, run the supported
   `scripts/windows/veridra-commercial-local.ps1` with positional command `backup`
   after following its documented local-operation procedure.
3. Run the same launcher with positional command `recovery-test`; it creates an
   isolated restore under `%LOCALAPPDATA%\\VeridraCommercial\\recovery-test-*`.
   Do **not** substitute live `data\\identity\\veridra.sqlite3` for the
   isolated restored SQLite file.
4. Identify the restored pair of paths in the same recovery-test directory:
   `identity\\veridra.sqlite3` and `tenants`.
5. From the repository root in PowerShell, inspect the restored pair (substitute
   the actual recovery-test folder):
   ```powershell
   python tools/webify_data_inventory.py `
     --identity-db "$env:LOCALAPPDATA\\VeridraCommercial\\recovery-test-YYYYMMDD_HHMMSS\\identity\\veridra.sqlite3" `
     --tenant-root "$env:LOCALAPPDATA\\VeridraCommercial\\recovery-test-YYYYMMDD_HHMMSS\\tenants"
   ```
6. Require `identity.state == "readable"` and
   `identity.integrity == "ok"`. `unsafe_snapshot` means WAL, SHM, or
   journal sidecars were found: do not infer missing records or delete
   anything; make a new consistent backup.
7. Review counts for projects, assessments, legacy workspace configs, plan
   history, and historical SaaS Stripe bindings. A zero count is evidence
   about the snapshot only, **not authorization to delete compatibility code**.
8. Retain the backup, original directory and the resulting summary. Do not
   paste customer files, passwords, Stripe secrets or the SQLite database into
   issues or pull requests.

The inventory performs counts only. It neither migrates nor repairs data,
and it does not establish full application-level restore compatibility by
itself. Release/merge still requires an operator acceptance using the
restored application data, including prospect-to-customer, reports and
Presence Care / customer billing where configured.

## Verified TRON evidence (2026-10-15/16)

- Verified quiesced backup and isolated recovery: 85 restored files; SQLite `quick_check=ok`.
- Read-only inventory: 1 user, 1 tenant, 1 tenant directory, 0 projects,
  0 assessments, 1 legacy workspace config, 1 historical SaaS Stripe binding,
  0 legacy plan events; no warnings.
- Isolated restored-data ASGI acceptance: `/agency` and `/health/live` HTTP 200;
  retired public SaaS routes HTTP 404; original source files unchanged.
- **NOT passed yet:** complete human workflow, real restart/worker persistence,
  independent second backup copy, provider-side status of historical Stripe binding.
- For the remaining business acceptance, use **synthetic/internal prospects only**.
  Do not send outreach, take real payments, or modify the original restored snapshot.

## Remaining full business workflow acceptance on TRON

The repository already ships `VERIDRA_OPERATOR_E2E_ACCEPTANCE.bat`.
It executes `tools/full_business_lifecycle_acceptance_entry.py`, which covers
synthetic prospect qualification, sales/proposals, customer/onboarding,
project and report delivery, remediation, monitoring, and the recurring-service
lifecycle. The CI `windows-portability` job runs this same batch script.

On TRON, from the updated `refactor/webify-operator-only` checkout:

```powershell
& .\VERIDRA_OPERATOR_E2E_ACCEPTANCE.bat
if ($LASTEXITCODE -ne 0) { throw 'Business lifecycle acceptance failed.' }
```

The script uses a temporary `LOCALAPPDATA` and synthetic contact/payment
references, and saves a ZIP evidence package under `Downloads`. It does not
need to contact a real prospect, charge a customer, or modify the existing
`VeridraCommercial` data directory. Do not upload evidence ZIPs without
checking them for sensitive material.

**Boundary:** this is the legacy operator E2E runner, not a human usability
sign-off or confirmation that the current `VeridraCommercial` runtime has
completed every workflow against the restored TRON snapshot. These remain
separate acceptance gates.
