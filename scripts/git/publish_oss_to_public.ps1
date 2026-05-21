# Sync OSS snapshot to public repo wemedia-baby (no proprietary paths)
# Run from repo root: .\scripts\git\publish_oss_to_public.ps1

$ErrorActionPreference = "Continue"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

$WorktreePath = Join-Path $RepoRoot ".git/oss-public-sync"
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
    param(
        [string]$WorkDir = $RepoRoot,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$GitArgs
    )
    Push-Location $WorkDir
    try {
        $output = & git @GitArgs 2>&1
        if ($LASTEXITCODE -ne 0) {
            $text = ($output | Out-String).Trim()
            Fail "git $($GitArgs -join ' ') failed: $text"
        }
        return $output
    } finally {
        Pop-Location
    }
}

# 1) clean working tree on main
$currentBranch = (Invoke-Git rev-parse --abbrev-ref HEAD | Out-String).Trim()
if ($currentBranch -ne "main") {
    Invoke-Git checkout main | Out-Null
}
$status = (Invoke-Git status --porcelain | Out-String).Trim()
if ($status) {
    Fail "Uncommitted changes on main. Commit or stash before running this script."
}

# 2) validate public remote
$publicUrl = (Invoke-Git remote get-url public | Out-String).Trim()
if ($publicUrl -match "wemedia-baby-Pro") {
    Fail "Remote 'public' points to private repo (wemedia-baby-Pro). Fix remotes first."
}
if ($publicUrl -notmatch "wemedia-baby") {
    Fail "Unexpected public remote URL: $publicUrl"
}

# 3) prepare isolated worktree (does not touch main working tree)
if (Test-Path $WorktreePath) {
    Invoke-Git worktree remove --force $WorktreePath | Out-Null
}
Invoke-Git worktree add -B oss-release $WorktreePath main | Out-Null

try {
    foreach ($rel in $OssExcludePaths) {
        $full = Join-Path $WorktreePath $rel
        if (Test-Path $full) {
            Push-Location $WorktreePath
            & git rm -r --cached --ignore-unmatch $rel 2>&1 | Out-Null
            Pop-Location
        }
    }

    $gitignorePath = Join-Path $WorktreePath ".gitignore"
    $gitignore = Get-Content $gitignorePath -Raw -Encoding UTF8
    if ($gitignore -notmatch "src/proprietary/") {
        Add-Content -Path $gitignorePath -Value $OssGitignoreBlock -Encoding UTF8
        Invoke-Git -WorkDir $WorktreePath add .gitignore | Out-Null
    }

    $pending = (Invoke-Git -WorkDir $WorktreePath status --porcelain | Out-String).Trim()
    if ($pending) {
        Invoke-Git -WorkDir $WorktreePath add -A | Out-Null
        Invoke-Git -WorkDir $WorktreePath commit -m "chore: OSS public sync snapshot" | Out-Null
        Write-Ok "Created oss-release commit in worktree."
    } else {
        Write-Warn "No changes on oss-release; skip commit."
    }

    Write-Info "Pushing oss-release to public/main..."
    Invoke-Git -WorkDir $WorktreePath push public oss-release:main | Out-Null
} finally {
    Invoke-Git worktree remove --force $WorktreePath | Out-Null
}

Write-Ok "Public sync done (main branch untouched): $publicUrl"
