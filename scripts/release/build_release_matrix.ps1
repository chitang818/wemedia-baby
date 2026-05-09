<#
.SYNOPSIS
    Build installers for selected editions (OSS / PRO / 52POJIE).

.DESCRIPTION
    This script only orchestrates existing build scripts with consistent flags.
    Keep all user-visible strings ASCII to avoid Windows PowerShell encoding issues.
#>

param (
    # Which edition(s) to build. Must be explicitly provided.
    [Parameter(Mandatory = $true)]
    [String[]]$DistMode,

    # Fast  = PyInstaller; Secure = Nuitka; Auto = OSS->Fast, PRO/52POJIE->Secure
    [ValidateSet("Auto", "Fast", "Secure")]
    [String]$BuildType = "Auto",

    [Switch]$RequireCleanInstall = $false,
    [Switch]$SkipInstaller = $false,
    # Do not use "-Debug" (reserved common parameter). Use "-BuildDebug" instead.
    [Switch]$BuildDebug = $false,
    [Switch]$FullRebuild = $false,
    [Switch]$SkipPipInstall = $false,

    # Print commands only; do not execute build.
    [Switch]$DryRun = $false
)

$ErrorActionPreference = "Stop"

function Normalize-DistModes([string[]]$modes) {
    $allowed = @("OSS", "PRO", "52POJIE")
    $set = New-Object System.Collections.Generic.HashSet[string]
    foreach ($m in $modes) {
        if (-not $m) { continue }
        foreach ($p in ($m -split ",")) {
            $v = $p.Trim().ToUpper()
            if (-not $v) { continue }
            if ($allowed -notcontains $v) {
                throw "Invalid DistMode: $v. Allowed: OSS, PRO, 52POJIE"
            }
            [void]$set.Add($v)
        }
    }
    return @($set)
}

function Get-EffectiveBuildType([string]$Mode) {
    if ($BuildType -ne "Auto") { return $BuildType }
    if ($Mode -eq "OSS") { return "Fast" }
    return "Secure"
}

function Invoke-Maybe([string]$Title, [string]$CommandLine, [scriptblock]$Action) {
    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor DarkGray
    Write-Host $Title -ForegroundColor Cyan
    Write-Host ("=" * 72) -ForegroundColor DarkGray
    Write-Host ("CMD: " + $CommandLine) -ForegroundColor DarkGray
    if ($DryRun) {
        Write-Host "DryRun: skipped." -ForegroundColor Yellow
        return
    }
    & $Action
}

function Invoke-Step([string]$Title, [scriptblock]$Action) {
    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor DarkGray
    Write-Host $Title -ForegroundColor Cyan
    Write-Host ("=" * 72) -ForegroundColor DarkGray
    & $Action
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = (Get-Item $ScriptDir).Parent.Parent.FullName
$BuildFast = Join-Path $ProjectRoot "scripts\\build\\build_fast.ps1"
$BuildNuitka = Join-Path $ProjectRoot "scripts\\build\\build_nuitka.ps1"

if (-not (Test-Path $BuildFast)) { throw "Missing: $BuildFast" }
if (-not (Test-Path $BuildNuitka)) { throw "Missing: $BuildNuitka" }

Set-Location $ProjectRoot

$Modes = Normalize-DistModes $DistMode
foreach ($m in $Modes) {
    $eff = Get-EffectiveBuildType $m
    if ($eff -eq "Fast") {
        $args = @()
        if ($RequireCleanInstall) { $args += "-RequireCleanInstall" }
        $cmd = ".\\scripts\\build\\build_fast.ps1 " + ($args -join " ") + " -DistMode $m"
        Invoke-Maybe ("Build " + $m + " (Fast / PyInstaller)") $cmd {
            & $BuildFast @args -DistMode $m
        }
    } else {
        $args = @()
        if ($RequireCleanInstall) { $args += "-RequireCleanInstall" }
        if ($SkipInstaller) { $args += "-SkipInstaller" }
        if ($BuildDebug) { $args += "-Debug" }
        if ($FullRebuild) { $args += "-FullRebuild" }
        if ($SkipPipInstall) { $args += "-SkipPipInstall" }
        $cmd = ".\\scripts\\build\\build_nuitka.ps1 " + ($args -join " ") + " -DistMode $m"
        Invoke-Maybe ("Build " + $m + " (Secure / Nuitka)") $cmd {
            & $BuildNuitka @args -DistMode $m
        }
    }
}

Write-Host ""
Write-Host "Done. Installers output: dist/installers/" -ForegroundColor Green

