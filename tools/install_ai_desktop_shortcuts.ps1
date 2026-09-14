$ErrorActionPreference = 'Stop'

$ThisRepo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$ReposParent = Split-Path $ThisRepo -Parent
$Desktop = [Environment]::GetFolderPath('Desktop')
$AssetRoot = Join-Path $env:LOCALAPPDATA 'RafaelAlbaWebify\AIProjectShortcuts'
$IconRoot = Join-Path $AssetRoot 'icons'
New-Item -ItemType Directory -Force -Path $IconRoot | Out-Null

Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class NativeIconCleanup {
    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    public extern static bool DestroyIcon(IntPtr handle);
}
'@

function Resolve-RepoPath {
    param([string[]]$Names)
    foreach ($name in $Names) {
        $candidate = Join-Path $ReposParent $name
        if (Test-Path (Join-Path $candidate 'AI_CONTEXT.bat')) {
            return (Resolve-Path $candidate).Path
        }
    }
    return $null
}

function New-LetterIcon {
    param(
        [Parameter(Mandatory)][string]$Letter,
        [Parameter(Mandatory)][string]$BackColor,
        [Parameter(Mandatory)][string]$OutputPath
    )

    $bitmap = New-Object System.Drawing.Bitmap 128,128
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    $graphics.Clear([System.Drawing.Color]::Transparent)

    $brush = New-Object System.Drawing.SolidBrush ([System.Drawing.ColorTranslator]::FromHtml($BackColor))
    $graphics.FillEllipse($brush, 4, 4, 120, 120)

    $font = New-Object System.Drawing.Font('Segoe UI', 70, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
    $textBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::White)
    $format = New-Object System.Drawing.StringFormat
    $format.Alignment = [System.Drawing.StringAlignment]::Center
    $format.LineAlignment = [System.Drawing.StringAlignment]::Center
    $graphics.DrawString($Letter, $font, $textBrush, (New-Object System.Drawing.RectangleF(0,0,128,124)), $format)

    $hIcon = $bitmap.GetHicon()
    try {
        $icon = [System.Drawing.Icon]::FromHandle($hIcon)
        $stream = [System.IO.File]::Open($OutputPath, [System.IO.FileMode]::Create)
        try { $icon.Save($stream) } finally { $stream.Dispose(); $icon.Dispose() }
    }
    finally {
        [NativeIconCleanup]::DestroyIcon($hIcon) | Out-Null
        $font.Dispose(); $textBrush.Dispose(); $brush.Dispose(); $format.Dispose(); $graphics.Dispose(); $bitmap.Dispose()
    }
}

$Projects = @(
    @{ Name='JOLT'; RepoNames=@('jolt','JOLT'); Letter='J'; Color='#2563EB'; Shortcut='JOLT - New AI Chat.lnk' },
    @{ Name='VERIDRA'; RepoNames=@('veridra','VERIDRA'); Letter='V'; Color='#059669'; Shortcut='VERIDRA - New AI Chat.lnk' },
    @{ Name='FORGE'; RepoNames=@('FORGE','forge'); Letter='F'; Color='#D97706'; Shortcut='FORGE - New AI Chat.lnk' }
)

$Shell = New-Object -ComObject WScript.Shell
$Failures = @()

Write-Host ''
Write-Host 'Installing AI project Desktop shortcuts...' -ForegroundColor Cyan
Write-Host "Repositories folder: $ReposParent"
Write-Host "Desktop: $Desktop"
Write-Host ''

foreach ($project in $Projects) {
    $repo = Resolve-RepoPath -Names $project.RepoNames
    if (-not $repo) {
        Write-Host "[MISSING] $($project.Name): AI_CONTEXT.bat not found under $ReposParent" -ForegroundColor Red
        $Failures += $project.Name
        continue
    }

    $iconPath = Join-Path $IconRoot ($project.Name.ToLowerInvariant() + '.ico')
    New-LetterIcon -Letter $project.Letter -BackColor $project.Color -OutputPath $iconPath

    $target = Join-Path $repo 'AI_CONTEXT.bat'
    $shortcutPath = Join-Path $Desktop $project.Shortcut
    $shortcut = $Shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $target
    $shortcut.WorkingDirectory = $repo
    $shortcut.IconLocation = "$iconPath,0"
    $shortcut.Description = "$($project.Name) - create ChatGPT project context and start a new AI chat"
    $shortcut.Save()

    $check = $Shell.CreateShortcut($shortcutPath)
    if ((Test-Path $shortcutPath) -and (Test-Path $check.TargetPath) -and (Test-Path ($check.IconLocation.Split(',')[0]))) {
        Write-Host "[OK] $($project.Name) -> $shortcutPath" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] $($project.Name) shortcut verification failed" -ForegroundColor Red
        $Failures += $project.Name
    }
}

Write-Host ''
if ($Failures.Count -eq 0) {
    Write-Host 'SUCCESS - All three Desktop shortcuts are installed and verified.' -ForegroundColor Green
    Write-Host ''
    Write-Host 'From now on, double-click the project shortcut:' -ForegroundColor White
    Write-Host '  JOLT - New AI Chat'
    Write-Host '  VERIDRA - New AI Chat'
    Write-Host '  FORGE - New AI Chat'
    exit 0
}

Write-Host ('FAILED/MISSING: ' + ($Failures -join ', ')) -ForegroundColor Red
Write-Host 'Pull/update the missing repository and run this installer again.'
exit 1
