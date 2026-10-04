$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$CommercialLauncher = Join-Path $PSScriptRoot 'veridra-commercial-local.ps1'
$Downloads = Join-Path $env:USERPROFILE 'Downloads'
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$SessionRoot = Join-Path $Downloads "VERIDRA_COMMERCIAL_H500_ACCEPTANCE_$Stamp"
$Evidence = Join-Path $SessionRoot 'evidence'
$Checklist = Join-Path $SessionRoot 'CHECKLIST.md'
$Defects = Join-Path $SessionRoot 'DEFECTS.md'
$Session = Join-Path $SessionRoot 'SESSION.txt'
$Decision = Join-Path $SessionRoot 'FINAL_DECISION.md'
$CommercialUrl = 'http://127.0.0.1:8011/'

function Write-Step([string]$Message) {
    Write-Host "[VERIDRA H500] $Message"
}

New-Item -ItemType Directory -Force -Path $SessionRoot,$Evidence | Out-Null

$branch = (& git -C $RepoRoot branch --show-current 2>$null)
$commit = (& git -C $RepoRoot rev-parse HEAD 2>$null)
$status = (& git -C $RepoRoot status --short 2>$null)
if (-not $branch) { $branch = 'unknown' }
if (-not $commit) { $commit = 'unknown' }
if (-not $status) { $status = '(clean or unavailable)' }

@"
WEBIFY · VERIDRA LOCAL-AGENCY H-500 HUMAN ACCEPTANCE
Session started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss K')
Repository: $RepoRoot
Branch: $branch
Commit: $commit
Operator machine: $env:COMPUTERNAME
Windows user: $env:USERNAME
Runtime target: VERIDRA_ENV=production + VERIDRA_LOCAL_AGENCY=1 / loopback-only Webify runtime
Expected URL: $CommercialUrl

Git working tree:
$status

Boundary:
- private Webify local-agency product only
- no VERIDRA SaaS signup, plan, billing or seat gate
- synthetic/internal acceptance data only
- no real outreach
- no direct DB/store mutation
- H6/H-400 SaaS-provider evidence is historical and is not a local-operation dependency
- automated regression acceptance does not satisfy this human H-500 gate
"@ | Set-Content -Path $Session -Encoding utf8

@'
# Webify · VERIDRA local-agency — H-500 human acceptance

Replace each `[ ] NOT TESTED` with `[x] PASS`, `[!] DEFECT`, or `[-] ACCEPTED GAP`.

Do not mark a human step PASS because repository CI or isolated Playwright acceptance passed.

## 1 — Production preflight and supervision
- [ ] NOT TESTED — `VERIDRA_COMMERCIAL_PREFLIGHT.bat` has no critical failures.
- [ ] NOT TESTED — `VERIDRA_COMMERCIAL_START.bat` starts the web runtime.
- [ ] NOT TESTED — Monitoring service is running.
- [ ] NOT TESTED — Durable crawl worker is running.
- [ ] NOT TESTED — Runtime is bound only to loopback.
- [ ] NOT TESTED — Commercial state is separate from the Webify/operator state root.
- [ ] NOT TESTED — `VERIDRA_COMMERCIAL_STATUS.bat` is understandable.

## 2 — Local identity and Webify product boundary
- [ ] NOT TESTED — Opening `/` enters the Webify local-agency console instead of a public/free/SaaS landing page.
- [ ] NOT TESTED — The single local Webify owner is resolved without a browser signup or login step.
- [ ] NOT TESTED — Prospecting/sales, inbound leads, customers, projects and Presence Care are discoverable from normal navigation.
- [ ] NOT TESTED — `/signup`, `/login`, `/plans`, `/billing` and `/workspace` are not exposed in the local-agency runtime.
- [ ] NOT TESTED — Normal local work is not blocked by a VERIDRA plan, seat allowance or SaaS usage quota.

## 3 — Client project and bounded audit
- [ ] NOT TESTED — Create or open a synthetic client project through supported UI.
- [ ] NOT TESTED — Quick/Standard/Deep project crawl choices are understandable.
- [ ] NOT TESTED — Run a bounded public audit through the normal project workflow.
- [ ] NOT TESTED — Audit progress/completion is clear.
- [ ] NOT TESTED — Saved findings are reviewable without raw-store access.
- [ ] NOT TESTED — Affected-page evidence is useful and understandable.

## 4 — White-label report / PDF
- [ ] NOT TESTED — Create or select a saved report profile.
- [ ] NOT TESTED — Agency identity/logo/colour/client fields render correctly.
- [ ] NOT TESTED — Human QA approval gate is clear.
- [ ] NOT TESTED — HTML report preview is professional and understandable.
- [ ] NOT TESTED — Affected-page lists are visible where relevant.
- [ ] NOT TESTED — PDF downloads successfully.
- [ ] NOT TESTED — PDF filename/branding is white-label where entitled.
- [ ] NOT TESTED — PDF pagination/TOC/findings layout is acceptable.

## 5 — Embedded lead generation
- [ ] NOT TESTED — Create a dedicated synthetic acceptance lead form.
- [ ] NOT TESTED — Do not configure a real notification recipient or external webhook for this acceptance form.
- [ ] NOT TESTED — Quick/Standard public audit depth is understandable.
- [ ] NOT TESTED — Deep/Custom are not exposed on the public lead form.
- [ ] NOT TESTED — Embed/setup instructions are understandable.
- [ ] NOT TESTED — Submit a synthetic lead through the public loopback form.
- [ ] NOT TESTED — Consent wording is visible and required.
- [ ] NOT TESTED — Configured thank-you copy is shown.
- [ ] NOT TESTED — Lead appears in the tenant lead inbox with source provenance.
- [ ] NOT TESTED — Lead CSV export downloads and contains the synthetic lead.

## 6 — Lead management / conversion
- [ ] NOT TESTED — Open the synthetic lead.
- [ ] NOT TESTED — Status/owner/next action/follow-up/notes are usable.
- [ ] NOT TESTED — Activity history records meaningful changes.
- [ ] NOT TESTED — Convert the lead to a client project through supported UI.
- [ ] NOT TESTED — Conversion is not duplicated if revisited.

## 7 — Remediation / monitoring
- [ ] NOT TESTED — Create a remediation task from a finding.
- [ ] NOT TESTED — Task owner/status/due date/notes are usable.
- [ ] NOT TESTED — Monitoring & comparison is discoverable.
- [ ] NOT TESTED — Enable/configure monitoring for the synthetic project.
- [ ] NOT TESTED — Execute or observe a monitoring run.
- [ ] NOT TESTED — Previous/latest comparison is understandable.

## 8 — Restart / persistence
- [ ] NOT TESTED — Stop the commercial runtime normally.
- [ ] NOT TESTED — Restart it normally.
- [ ] NOT TESTED — Workspace/project/assessment/report/lead/task/monitoring state persists.
- [ ] NOT TESTED — All three supervised processes return to healthy state.

## 9 — Backup / independent copy / recovery
- [ ] NOT TESTED — Create a quiesced commercial backup with `VERIDRA_COMMERCIAL_BACKUP.bat`.
- [ ] NOT TESTED — Verify the produced backup exists and is non-empty.
- [ ] NOT TESTED — Copy the backup to an independent operator-controlled location/device.
- [ ] NOT TESTED — Run the supported isolated `recovery-test`.
- [ ] NOT TESTED — Recovery test reports SQLite integrity success.
- [ ] NOT TESTED — Active commercial state is not overwritten by the recovery test.

## 10 — Optional integrations and legacy-provider isolation
- [ ] NOT TESTED — Normal Webify local startup does not require or load VERIDRA SaaS Stripe billing.
- [ ] NOT TESTED — Existing H6/H-400 Stripe sandbox evidence is retained as historical acceptance, not presented as a current operating dependency.
- [ ] NOT TESTED — Legacy Stripe configuration, if still present on disk, does not gate normal local startup or features.
- [ ] NOT TESTED — No provider secret appears in captured acceptance evidence.
- [ ] NOT TESTED — SMTP is explicitly recorded as enabled+tested for an intentional workflow or disabled; absence is not misreported as a product failure.

## 11 — Whole-product judgment
- [ ] NOT TESTED — Navigation is understandable without remembered URLs.
- [ ] NOT TESTED — No SaaS signup, plan, billing or seat-limit dead end appears in normal Webify navigation.
- [ ] NOT TESTED — Error/success feedback is clear.
- [ ] NOT TESTED — No P0/P1 functional defect remains.
- [ ] NOT TESTED — No unsafe or surprising default was found.
- [ ] NOT TESTED — The Webify local-agency product is usable for controlled local operation.

## Final H-500 decision
- [ ] NOT TESTED — All defects are fixed/retested or consciously accepted.
- [ ] NOT TESTED — I explicitly approve H-500 local commercial runtime acceptance.
'@ | Set-Content -Path $Checklist -Encoding utf8

@'
# H-500 defect log

Use one section per defect.

## H500-001 — Short title
- Checklist section:
- Screen / URL:
- Severity: P0 blocker / P1 important / P2 polish
- Expected:
- Actual:
- Why it matters:
- Evidence file / screenshot:
- Status: open
- Fix:
- Retest:
'@ | Set-Content -Path $Defects -Encoding utf8

@'
# H-500 final decision

Decision: NOT YET APPROVED

Complete only after the checklist is personally exercised.

- Operator:
- Date/time:
- Commit:
- Result: PASS / FAIL / PASS WITH ACCEPTED GAPS
- Open P0 defects:
- Open P1 defects:
- Accepted gaps:
- Notes:
'@ | Set-Content -Path $Decision -Encoding utf8

Write-Step "Session folder: $SessionRoot"
Write-Step 'Running Webify local-agency production preflight and capturing output...'
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $CommercialLauncher preflight *>&1 |
        Tee-Object -FilePath (Join-Path $Evidence 'preflight.txt') | Out-Host
} catch {
    $_ | Out-String | Set-Content -Path (Join-Path $Evidence 'preflight-error.txt') -Encoding utf8
    Write-Warning 'Preflight reported an error. Record it in DEFECTS.md; the session remains open for diagnosis.'
}

Write-Step 'Starting the supported Webify local-agency runtime...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $CommercialLauncher start

Write-Step 'Capturing managed-process status...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $CommercialLauncher status *>&1 |
    Tee-Object -FilePath (Join-Path $Evidence 'status.txt') | Out-Host

Start-Process $CommercialUrl
Start-Process notepad.exe -ArgumentList $Checklist
Start-Process notepad.exe -ArgumentList $Defects
Start-Process explorer.exe -ArgumentList $SessionRoot

Write-Host ''
Write-Host '======================================================'
Write-Host 'WEBIFY · VERIDRA LOCAL-AGENCY H-500 SESSION READY'
Write-Host '======================================================'
Write-Host "Checklist : $Checklist"
Write-Host "Defects   : $Defects"
Write-Host "Decision  : $Decision"
Write-Host "Evidence  : $Evidence"
Write-Host ''
Write-Host 'Use synthetic/internal acceptance data only. No real outreach.'
Write-Host 'Do not mark automated evidence as a human PASS.'
