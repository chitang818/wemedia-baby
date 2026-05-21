# Install pre-push hook (blocks: git push public main)
# Usage: .\scripts\git\install_git_hooks.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$SrcHook = Join-Path $PSScriptRoot "hooks/pre-push"
$DstHook = Join-Path $RepoRoot ".git/hooks/pre-push"

if (-not (Test-Path (Join-Path $RepoRoot ".git"))) {
    Write-Host "[ERROR] Not a git repo: $RepoRoot" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $SrcHook)) {
    Write-Host "[ERROR] Hook template missing: $SrcHook" -ForegroundColor Red
    exit 1
}

$hookText = (Get-Content -Path $SrcHook -Raw) -replace "`r`n", "`n"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($DstHook, $hookText, $utf8NoBom)
Write-Host "[OK] Installed pre-push hook: $DstHook" -ForegroundColor Green
Write-Host "[INFO] Blocks: git push public main. Use publish_oss_to_public.ps1 for OSS sync." -ForegroundColor Cyan
