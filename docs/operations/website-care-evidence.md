# Website Care evidence: first local integration seam

This is **not yet** a VERIDRA UI or a production client-facing service. It creates a dedicated operator-local SQLite evidence database independent of VERIDRA's working customer database. Only the existing `webify_wordpress_care_cycle_v1` lab evidence contract is accepted. Static/custom adapters require their own validated evidence contracts.

## TRON acceptance in one PowerShell session

Run in a clean checkout of the PR branch (or after merge), from the repository root. This uses the existing cycle report without rerunning backups:

```powershell
$Lab = "$HOME\Documents\WebifyLabs\wordpress-care"
$Evidence = Get-ChildItem "$Lab\acceptance\care-cycle\cycle-*.json" | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
$Ledger = "$Lab\acceptance\website-care-ledger.sqlite"
python -m veridra.website_care_evidence "$Evidence" --db "$Ledger" --website-ref lab-wordpress-8088 --platform wordpress
if ($LASTEXITCODE -ne 0) { throw "Website Care evidence import failed" }
python -m veridra.website_care_history --db "$Ledger" --website-ref lab-wordpress-8088
if ($LASTEXITCODE -ne 0) { throw "Website Care history query failed" }
```

Run the importer twice to verify idempotency; the second response must report `duplicate: true`. The database retains minimal normalized run metadata and an evidence SHA, **not raw archive contents, site passwords or customer records**.

No site-monitoring changes, credentials, remote modifications, backup scheduling or customer linkage are introduced here. Next steps require mapping to existing VERIDRA client/project records after schema review and operator authorization, implementing production-safe backups and retention, and separate technology-specific adapters.
