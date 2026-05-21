# Sync OSS snapshot to public repo wemedia-baby (no proprietary paths)
# Run from repo root: .\scripts\git\publish_oss_to_public.ps1

$ErrorActionPreference = "Continue"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

$OssExcludePaths = @(
    "docs",
    "src/proprietary",
    "src/plugins/pro",
    "src/pro_features"
)

$OssGitignoreBlock = @"

# --- OSS public sync: excluded on oss-release only ---
docs/
src/proprietary/
src/plugins/pro/
src/pro_features/
"@

function Write-Info([string]$Message) { Write-Host "[INFO] $Message" -ForegroundColor Cyan }
function Write-Ok([string]$Message) { Write-Host "[OK]   $Message" -ForegroundColor Green }
function Write-Warn([string]$Message) { Write-Host "[WARN] $Message" -ForegroundColor Yellow }
function Fail([string]$Message) {
    Write-Host "[ERROR] $Message" -ForegroundColor Red
    exit 1
}

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    $output = & git @Args 2>&1
    if ($LASTEXITCODE -ne 0) {
        $text = ($output | Out-String).Trim()
        Fail "git $($Args -join ' ') failed: $text"
    }
    return $output
}

# 1) clean working tree
$status = (Invoke-Git status --porcelain | Out-String).Trim()
if ($status) {
    Fail "Uncommitted changes detected. Commit or stash before running this script."
}

# 2) validate public remote
$publicUrl = (Invoke-Git remote get-url public | Out-String).Trim()
if ($publicUrl -match "wemedia-baby-Pro") {
    Fail "Remote 'public' points to private repo (wemedia-baby-Pro). Fix remotes first."
}
if ($publicUrl -notmatch "wemedia-baby") {
    Fail "Unexpected public remote URL: $publicUrl"
}

$currentBranch = (Invoke-Git branch --show-current | Out-String).Trim()
if ($currentBranch -ne "main") {
    Write-Warn "Not on main (current: $currentBranch). oss-release will be built from main."
}

Write-Info "Updating oss-release from main..."
Invoke-Git checkout -B oss-release main | Out-Null

foreach ($rel in $OssExcludePaths) {
    $full = Join-Path $RepoRoot $rel
    if (Test-Path $full) {
        & git rm -r --cached --ignore-unmatch $rel 2>&1 | Out-Null
    }
}

$gitignorePath = Join-Path $RepoRoot ".gitignore"
$gitignore = Get-Content $gitignorePath -Raw -Encoding UTF8
if ($gitignore -notmatch "src/proprietary/") {
    Add-Content -Path $gitignorePath -Value $OssGitignoreBlock -Encoding UTF8
    Invoke-Git add .gitignore | Out-Null
}

$pending = (Invoke-Git status --porcelain | Out-String).Trim()
if ($pending) {
    Invoke-Git add -A | Out-Null
    Invoke-Git commit -m "chore: OSS public sync snapshot" | Out-Null
    Write-Ok "Created oss-release commit."
} else {
    Write-Warn "No changes on oss-release; skip commit."
}

Write-Info "Pushing oss-release to public/main..."
Invoke-Git push public oss-release:main | Out-Null

Invoke-Git checkout main | Out-Null
Write-Ok "Back on main. Public sync done: $publicUrl"
