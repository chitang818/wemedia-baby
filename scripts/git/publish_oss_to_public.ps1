# 将开源快照同步到公开仓 wemedia-baby（不含闭源目录）
# 用法：在项目根目录执行 .\scripts\git\publish_oss_to_public.ps1

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

$OssExcludePaths = @(
    "docs",
    "src/proprietary",
    "src/plugins/pro",
    "src/pro_features"
)

$OssGitignoreBlock = @"

# --- OSS 公开仓同步：以下路径仅存在于 oss-release，main（私有主仓）可跟踪 ---
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

# 1) 工作区须干净
$status = git status --porcelain
if ($status) {
    Fail "工作区有未提交改动，请先 commit 或 stash 后再运行本脚本。"
}

# 2) 校验 public 远程，防止推到 Pro 私有仓
$publicUrl = (git remote get-url public 2>$null)
if (-not $publicUrl) { Fail "未找到远程 public，请先配置：git remote add public <开源仓 URL>" }
if ($publicUrl -match "wemedia-baby-Pro") {
    Fail "public 远程指向了私有仓（wemedia-baby-Pro），请修正后再运行。"
}
if ($publicUrl -notmatch "wemedia-baby") {
    Fail "public 远程 URL 异常：$publicUrl"
}

$currentBranch = git branch --show-current
if ($currentBranch -ne "main") {
    Write-Warn "当前不在 main 分支（当前：$currentBranch），将从 main 生成 oss-release。"
}

Write-Info "基于 main 更新 oss-release 分支..."
git checkout -B oss-release main

# 3) 从索引移除闭源路径（保留本地工作区文件）
foreach ($rel in $OssExcludePaths) {
    $full = Join-Path $RepoRoot $rel
    if (Test-Path $full) {
        git rm -r --cached --ignore-unmatch $rel 2>$null | Out-Null
    }
}

# 4) 在 oss-release 恢复开源版 .gitignore 规则
$gitignorePath = Join-Path $RepoRoot ".gitignore"
$gitignore = Get-Content $gitignorePath -Raw -Encoding UTF8
if ($gitignore -notmatch "src/proprietary/") {
    Add-Content -Path $gitignorePath -Value $OssGitignoreBlock -Encoding UTF8
    git add .gitignore
}

# 5) 提交快照（无变更则跳过）
$pending = git status --porcelain
if ($pending) {
    git add -A
    git commit -m "chore: OSS 公开仓同步快照"
    Write-Ok "已创建 oss-release 提交。"
} else {
    Write-Warn "oss-release 与上次快照无差异，跳过提交。"
}

# 6) 推送到公开仓
Write-Info "推送到 public（oss-release -> main）..."
git push public oss-release:main

git checkout main
Write-Ok "已切回 main。公开仓同步完成：$publicUrl"
