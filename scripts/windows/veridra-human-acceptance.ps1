$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$LocalLauncher = Join-Path $PSScriptRoot 'veridra-local.ps1'
$Downloads = Join-Path $env:USERPROFILE 'Downloads'
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$SessionRoot = Join-Path $Downloads "VERIDRA_HUMAN_ACCEPTANCE_$Stamp"
$Screenshots = Join-Path $SessionRoot 'screenshots'
$Diagnostics = Join-Path $SessionRoot 'diagnostics'
$Checklist = Join-Path $SessionRoot 'CHECKLIST.md'
$Defects = Join-Path $SessionRoot 'DEFECTS.md'
$Session = Join-Path $SessionRoot 'SESSION.txt'

function Write-Step([string]$Message) {
    Write-Host "[VERIDRA HUMAN ACCEPTANCE] $Message"
}

New-Item -ItemType Directory -Force -Path $SessionRoot,$Screenshots,$Diagnostics | Out-Null

$branch = (& git -C $RepoRoot branch --show-current 2>$null)
$commit = (& git -C $RepoRoot rev-parse HEAD 2>$null)
$status = (& git -C $RepoRoot status --short 2>$null)
if (-not $branch) { $branch = 'unknown' }
if (-not $commit) { $commit = 'unknown' }
if (-not $status) { $status = '(clean or unavailable)' }

$sessionText = @"
VERIDRA FULL-PRODUCT HUMAN OPERATOR ACCEPTANCE
Session started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss K')
Repository: $RepoRoot
Branch: $branch
Commit: $commit
Operator machine: $env:COMPUTERNAME
Windows user: $env:USERNAME

Git working tree:
$status

Boundary:
- synthetic/internal data only
- no real outreach
- no direct DB/store mutation
- automated E2E does not complete this human gate

Issue: #279
"@
Set-Content -Path $Session -Value $sessionText -Encoding utf8

$checklistText = @'
# VERIDRA — Human full-product acceptance

Session rule: personally exercise every item. Do not mark PASS because an automated test previously passed.

Status syntax: replace `[ ] NOT TESTED` with `[x] PASS`, `[!] DEFECT`, or `[-] ACCEPTED GAP`.

## 1 — Startup / identity
- [ ] NOT TESTED — Normal local launch works from the supported launcher.
- [ ] NOT TESTED — First-use/onboarding path is understandable.
- [ ] NOT TESTED — Workspace creation works through UI.
- [ ] NOT TESTED — Login works.
- [ ] NOT TESTED — Logout works.
- [ ] NOT TESTED — Re-login works.
- [ ] NOT TESTED — Workspace/plan state is understandable and persists.
- [ ] NOT TESTED — STATUS output is understandable.
- [ ] NOT TESTED — DIAGNOSTICS output is useful.

## 2 — Agency home / navigation
- [ ] NOT TESTED — Agency home/dashboard is understandable without remembering URLs.
- [ ] NOT TESTED — Major areas are discoverable from visible navigation.
- [ ] NOT TESTED — Empty/first-use states explain what to do next.
- [ ] NOT TESTED — No important workflow requires a guessed URL.

## 3 — Discovery -> prospect
- [ ] NOT TESTED — Supported discovery path can be located and understood.
- [ ] NOT TESTED — Evidence is reviewable before persistence.
- [ ] NOT TESTED — Synthetic prospect can be created/ingested through supported UI.
- [ ] NOT TESTED — Qualification controls and scoring meaning are understandable.
- [ ] NOT TESTED — Evidence, notes, follow-up and activity history are visible.

## 4 — Commercial lifecycle (synthetic only)
- [ ] NOT TESTED — Move prospect to contacted without sending a message.
- [ ] NOT TESTED — Move to responded/conversation/proposal manually.
- [ ] NOT TESTED — Offer/cohort/next action/follow-up controls are understandable.
- [ ] NOT TESTED — Loss reason path is understandable without actually losing the main synthetic customer.
- [ ] NOT TESTED — Won conversion creates expected customer state.

## 5 — Customer / onboarding
- [ ] NOT TESTED — Customer page gives useful identity/contact/commercial context.
- [ ] NOT TESTED — Onboarding checklist is clear and completable.
- [ ] NOT TESTED — Customer status behavior is understandable.
- [ ] NOT TESTED — No-site customer path is understandable.

## 6 — Project creation / linkage
- [ ] NOT TESTED — Create and link project from customer workflow.
- [ ] NOT TESTED — Customer -> project navigation works.
- [ ] NOT TESTED — Project -> customer navigation works.
- [ ] NOT TESTED — Project overview makes the next action obvious.

## 7 — Assessment / evidence
- [ ] NOT TESTED — Run assessment through normal UI.
- [ ] NOT TESTED — Saved findings are easy to locate.
- [ ] NOT TESTED — Direct observations and findings/interpretation are distinguishable.
- [ ] NOT TESTED — Error/unavailable evidence is not presented misleadingly.
- [ ] NOT TESTED — Evidence detail is understandable to an operator.

## 8 — Review Intelligence
- [ ] NOT TESTED — Review Intelligence operator entry point is discoverable.
- [ ] NOT TESTED — Previously accepted/safe review evidence can be inspected.
- [ ] NOT TESTED — Sample bounds, statistics and provenance are understandable.
- [ ] NOT TESTED — Deterministic output does not present sentiment/theme/fake-review inference.
- [ ] NOT TESTED — Review artifact/acceptance output is understandable.

## 9 — AI review exchange
- [ ] NOT TESTED — AI review exchange entry point is discoverable.
- [ ] NOT TESTED — Export standard AI review JSON through UI.
- [ ] NOT TESTED — Operator instructions make the external ChatGPT step clear.
- [ ] NOT TESTED — Import a synthetic valid reviewed result.
- [ ] NOT TESTED — AI interpretation vs VERIDRA evidence is visually obvious.
- [ ] NOT TESTED — Source binding/evidence refs are understandable.
- [ ] NOT TESTED — Safe actions remain advisory/inert.

## 10 — Remediation / tasks
- [ ] NOT TESTED — Create remediation task from a saved finding.
- [ ] NOT TESTED — Set owner/status/due date/notes.
- [ ] NOT TESTED — Update/verify task state.
- [ ] NOT TESTED — Task links back to project/finding/evidence coherently.

## 11 — Reports
- [ ] NOT TESTED — Configure branded report profile.
- [ ] NOT TESTED — Preview report.
- [ ] NOT TESTED — Download PDF.
- [ ] NOT TESTED — Inspect PDF visually for professional/usability defects.
- [ ] NOT TESTED — Test safe/local report delivery only.
- [ ] NOT TESTED — Delivery attempt/status is visible.

## 12 — Monitoring / longitudinal progress
- [ ] NOT TESTED — Enable monitoring.
- [ ] NOT TESTED — Run monitoring now.
- [ ] NOT TESTED — Configure autonomous cadence.
- [ ] NOT TESTED — Observe autonomous run actually execute.
- [ ] NOT TESTED — Latest/previous assessment navigation is clear.
- [ ] NOT TESTED — Progress / Changes is easy to find.
- [ ] NOT TESTED — New/resolved/persistent/page-change language is understandable.

## 13 — Billing
- [ ] NOT TESTED — Record invoice reference/amount/currency/dates/payment state.
- [ ] NOT TESTED — External-accounting invoice boundary is clear.
- [ ] NOT TESTED — Billing state is visible from customer workflow.
- [ ] NOT TESTED — Billing state is visible in management/dashboard views.

## 14 — Management views
- [ ] NOT TESTED — Funnel KPIs are understandable.
- [ ] NOT TESTED — Follow-up queue is understandable and navigable.
- [ ] NOT TESTED — Customers view is useful.
- [ ] NOT TESTED — Projects view is useful.
- [ ] NOT TESTED — Tasks/remediation view is useful.
- [ ] NOT TESTED — Counts/cards lead somewhere useful where expected.

## 15 — Persistence / restart
- [ ] NOT TESTED — Stop VERIDRA normally.
- [ ] NOT TESTED — Restart normally.
- [ ] NOT TESTED — Synthetic prospect/customer/project state remains visible.
- [ ] NOT TESTED — Assessment/task/report/monitoring/billing state remains visible.

## 16 — Backup / restore
- [ ] NOT TESTED — Create supported backup.
- [ ] NOT TESTED — Mutate synthetic state through UI.
- [ ] NOT TESTED — Preview supported restore.
- [ ] NOT TESTED — Apply supported restore.
- [ ] NOT TESTED — Restart.
- [ ] NOT TESTED — Restored state is visibly recovered through UI.

## 17 — Whole-app UX judgment
- [ ] NOT TESTED — Wording is understandable without developer knowledge.
- [ ] NOT TESTED — Primary actions are visually obvious.
- [ ] NOT TESTED — Click count feels reasonable.
- [ ] NOT TESTED — Screen hierarchy/grouping is clear.
- [ ] NOT TESTED — Navigation/back paths are sufficient.
- [ ] NOT TESTED — Loading/success/error feedback is clear.
- [ ] NOT TESTED — No unsafe/surprising defaults found.
- [ ] NOT TESTED — No duplicate/conflicting concepts found.
- [ ] NOT TESTED — Overall workflow is acceptable for real-world validation.

## Final operator decision
- [ ] NOT TESTED — All defects fixed/retested or consciously accepted/backlogged.
- [ ] NOT TESTED — I explicitly approve moving VERIDRA to real-world validation.
'@
Set-Content -Path $Checklist -Value $checklistText -Encoding utf8

$defectText = @'
# VERIDRA — Human acceptance defect log

Record problems instead of working around them.

## Defect template

### HUX-001 — Short title
- Section:
- Screen / URL:
- Severity: P0 blocker / P1 important / P2 polish
- Type: functional / navigation / wording / hierarchy / excessive-clicks / feedback / safety / visual / other
- What I expected:
- What happened:
- Why it matters to a first-time operator:
- Screenshot: screenshots/<filename>.png
- Status: open
- Fix / accepted decision:
- Retest result:

---

## Defects

'@
Set-Content -Path $Defects -Value $defectText -Encoding utf8

Write-Step "Session folder: $SessionRoot"
Write-Step "Commit under test: $commit"
Write-Step 'Starting VERIDRA using the supported local launcher...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $LocalLauncher open
if ($LASTEXITCODE -ne 0) {
    throw "VERIDRA failed to open (exit $LASTEXITCODE)."
}

try {
    Write-Step 'Capturing initial diagnostics...'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $LocalLauncher diagnostics | Out-Host
    $runtimeRoot = Join-Path $env:LOCALAPPDATA 'Veridra\runtime'
    $latest = Get-ChildItem $runtimeRoot -Filter 'VERIDRA_DIAGNOSTICS_*.txt' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($latest) {
        Copy-Item $latest.FullName (Join-Path $Diagnostics $latest.Name) -Force
    }
} catch {
    Write-Warning "Initial diagnostics could not be copied: $($_.Exception.Message)"
}

Start-Process notepad.exe -ArgumentList $Checklist
Start-Process notepad.exe -ArgumentList $Defects
Start-Process explorer.exe -ArgumentList $SessionRoot

Write-Host ''
Write-Host '======================================================'
Write-Host 'VERIDRA HUMAN ACCEPTANCE SESSION READY'
Write-Host '======================================================'
Write-Host "Checklist : $Checklist"
Write-Host "Defects   : $Defects"
Write-Host "Screenshots: $Screenshots"
Write-Host ''
Write-Host 'Use synthetic/internal data only. No real outreach.'
Write-Host 'Do not mark automated evidence as a human PASS.'
Write-Host 'Issue #279 closes only after the complete manual walkthrough.'
