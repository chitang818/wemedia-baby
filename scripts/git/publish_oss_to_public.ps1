# Sync OSS snapshot to public repo wemedia-baby (no proprietary paths)
# Run from repo root: .\scripts\git\publish_oss_to_public.ps1

$ErrorActionPreference = "Continue"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
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

function Run-GitIn([string]$Dir, [string[]]$GitArgs) {
    Push-Location $Dir
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

Set-Location $RepoRoot

# 1) ensure on main with clean tree
$branch = (Run-GitIn $RepoRoot @("symbolic-ref", "--short", "HEAD") | Out-String).Trim()
if ($branch -ne "main") {
    Run-GitIn $RepoRoot @("checkout", "main") | Out-Null
}
$status = (Run-GitIn $RepoRoot @("status", "--porcelain") | Out-String).Trim()
if ($status) {
    Fail "Uncommitted changes on main. Commit or stash before running this script."
}

# 2) validate public remote
$publicUrl = (Run-GitIn $RepoRoot @("remote", "get-url", "public") | Out-String).Trim()
if ($publicUrl -match "wemedia-baby-Pro") {
    Fail "Remote 'public' points to private repo (wemedia-baby-Pro). Fix remotes first."
}
if ($publicUrl -notmatch "wemedia-baby") {
    Fail "Unexpected public remote URL: $publicUrl"
}

# 3) build oss-release in isolated worktree
if (Test-Path $WorktreePath) {
    Run-GitIn $RepoRoot @("worktree", "remove", "--force", $WorktreePath) | Out-Null
}
Run-GitIn $RepoRoot @("worktree", "add", "-B", "oss-release", $WorktreePath, "main") | Out-Null

try {
    foreach ($rel in $OssExcludePaths) {
        if (Test-Path (Join-Path $WorktreePath $rel)) {
            Run-GitIn $WorktreePath @("rm", "-r", "--cached", "--ignore-unmatch", $rel) | Out-Null
        }
    }

    $gitignorePath = Join-Path $WorktreePath ".gitignore"
    $gitignore = Get-Content $gitignorePath -Raw -Encoding UTF8
    if ($gitignore -notmatch "src/proprietary/") {
        Add-Content -Path $gitignorePath -Value $OssGitignoreBlock -Encoding UTF8
        Run-GitIn $WorktreePath @("add", ".gitignore") | Out-Null
    }

    $pending = (Run-GitIn $WorktreePath @("status", "--porcelain") | Out-String).Trim()
    if ($pending) {
        Run-GitIn $WorktreePath @("add", "-A") | Out-Null
        Push-Location $WorktreePath
        try {
            & git commit -m "chore: OSS public sync snapshot" 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                $porcelain = (git status --porcelain | Out-String).Trim()
                if ($porcelain) { Fail "git commit failed on oss-release." }
                Write-Warn "No commit created (already up to date)."
            } else {
                Write-Ok "Created oss-release commit in worktree."
            }
        } finally {
            Pop-Location
        }
    } else {
        Write-Warn "No changes on oss-release; skip commit."
    }

    Write-Info "Pushing oss-release to public/main..."
    Run-GitIn $WorktreePath @("push", "public", "oss-release:main") | Out-Null
} finally {
    Run-GitIn $RepoRoot @("worktree", "remove", "--force", $WorktreePath) | Out-Null
}

Write-Ok "Public sync done (main branch untouched): $publicUrl"
