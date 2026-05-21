# Sync OSS snapshot to public repo (excludes proprietary paths)
# Usage: .\scripts\git\publish_oss_to_public.ps1
#        .\scripts\git\publish_oss_to_public.ps1 -DryRun

param(
    [switch]$DryRun
)

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

# --- OSS public sync: excluded on oss-release snapshot branch ---
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

function Invoke-GitCommand {
    param(
        [string]$Cwd = $RepoRoot,
        [Parameter(Mandatory = $true)]
        [string[]]$GitArguments
    )
    $output = & git -C $Cwd @GitArguments 2>&1
    $code = $LASTEXITCODE
    $text = @($output | ForEach-Object { "$_" }) -join "`n"
    return @{ Code = $code; Text = $text.Trim() }
}

function Require-GitCommand {
    param(
        [string]$Cwd = $RepoRoot,
        [string[]]$GitArguments,
        [string]$Hint = ""
    )
    $r = Invoke-GitCommand -Cwd $Cwd -GitArguments $GitArguments
    if ($r.Code -ne 0) {
        $msg = "git $($GitArguments -join ' ') failed: $($r.Text)"
        if ($Hint) { $msg += "`n$Hint" }
        Fail $msg
    }
    return $r.Text
}

function Test-SnapshotHasExcludedPaths([string]$Cwd) {
    $tree = Require-GitCommand -Cwd $Cwd -GitArguments @("rev-parse", "HEAD")
    $files = Require-GitCommand -Cwd $Cwd -GitArguments @("ls-tree", "-r", "--name-only", $tree)
    foreach ($line in ($files -split "`n")) {
        if (-not $line) { continue }
        foreach ($prefix in $OssExcludePaths) {
            $p = $prefix.Replace("\", "/")
            if ($line -eq $p -or $line.StartsWith("$p/")) {
                return $line
            }
        }
    }
    return $null
}

Set-Location $RepoRoot

Write-Info "Repo: $RepoRoot"

$branch = Require-GitCommand -GitArguments @("symbolic-ref", "--short", "HEAD")
if ($branch -ne "main") {
    Write-Warn "Switching to main (was: $branch)"
    Require-GitCommand -GitArguments @("checkout", "main") | Out-Null
}

$status = Require-GitCommand -GitArguments @("status", "--porcelain")
if ($status) {
    Fail "Uncommitted changes on main. Commit or stash first, then run this script again."
}

$ahead = Invoke-GitCommand -GitArguments @("rev-list", "--count", "origin/main..main")
if ($ahead.Code -eq 0 -and [int]$ahead.Text -gt 0) {
    Write-Warn "main is $ahead.Text commit(s) ahead of origin/main. Consider: git push origin main"
}

$publicRemote = Invoke-GitCommand -GitArguments @("remote", "get-url", "public")
if ($publicRemote.Code -ne 0) {
    Fail "Remote 'public' not found. Run: git remote add public https://github.com/chitang818/wemedia-baby.git"
}
$publicUrl = $publicRemote.Text
if ($publicUrl -match "wemedia-baby-Pro") {
    Fail "Remote 'public' points to private repo. Fix remotes before sync."
}
if ($publicUrl -notmatch "wemedia-baby") {
    Fail "Unexpected public remote URL: $publicUrl"
}

if (Test-Path $WorktreePath) {
    Require-GitCommand -GitArguments @("worktree", "remove", "--force", $WorktreePath) | Out-Null
}
Require-GitCommand -GitArguments @("worktree", "add", "-B", "oss-release", $WorktreePath, "main") | Out-Null

try {
    $gitignorePath = Join-Path $WorktreePath ".gitignore"
    $gitignore = Get-Content $gitignorePath -Raw -Encoding UTF8
    if ($gitignore -notmatch "src/proprietary/") {
        Add-Content -Path $gitignorePath -Value $OssGitignoreBlock -Encoding UTF8
        Require-GitCommand -Cwd $WorktreePath -GitArguments @("add", ".gitignore") | Out-Null
    }

    foreach ($rel in $OssExcludePaths) {
        if (Test-Path (Join-Path $WorktreePath $rel)) {
            Invoke-GitCommand -Cwd $WorktreePath -GitArguments @("rm", "-r", "--cached", "--ignore-unmatch", $rel) | Out-Null
        }
    }

    $pending = Require-GitCommand -Cwd $WorktreePath -GitArguments @("status", "--porcelain")
    if ($pending) {
        $r = Invoke-GitCommand -Cwd $WorktreePath -GitArguments @("commit", "-m", "chore: OSS public sync snapshot")
        if ($r.Code -ne 0) {
            $still = Invoke-GitCommand -Cwd $WorktreePath -GitArguments @("status", "--porcelain")
            if ($still) { Fail "oss-release commit failed: $($r.Text)" }
            Write-Warn "No new commit (snapshot unchanged)."
        } else {
            $sha = Require-GitCommand -Cwd $WorktreePath -GitArguments @("rev-parse", "--short", "HEAD")
            Write-Ok "oss-release commit: $sha"
        }
    } else {
        Write-Warn "No index changes besides excluded paths; skip commit."
    }

    $leaked = Test-SnapshotHasExcludedPaths -Cwd $WorktreePath
    if ($leaked) {
        Fail "Snapshot check failed, excluded path still present: $leaked"
    }
    Write-Ok "Snapshot OK (no docs/, proprietary/, plugins/pro/, pro_features/)."

    if ($DryRun) {
        Write-Warn "DryRun: push skipped. Run without -DryRun to publish."
        return
    }

    Write-Info "Pushing to $publicUrl (oss-release -> main, force-with-lease)..."
    Require-GitCommand -Cwd $WorktreePath -GitArguments @(
        "push", "--force-with-lease", "public", "oss-release:main"
    ) | Out-Null
} finally {
    Require-GitCommand -GitArguments @("worktree", "remove", "--force", $WorktreePath) | Out-Null
}

Write-Ok "Public OSS repo synced. Local main and proprietary files unchanged."
Write-Info "Do NOT use: git push public main. Use: git push origin main for private repo."
