# 记录启动耗时基线（需已安装项目依赖）
# 用法: .\scripts\startup\record_startup_baseline.ps1
# 输出: test-reports/startup-baseline/README.md 与各模式日志片段说明

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root

$env:ENABLE_STARTUP_PROFILER = "1"
$env:ENABLE_PAGE_LOAD_PROFILER = "1"

$ReportDir = Join-Path $Root "test-reports\startup-baseline"
New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null

$modes = @("off", "minimal", "full")
$lines = @(
    "# 启动耗时基线记录",
    "",
    "生成方式: ``scripts/startup/record_startup_baseline.ps1``",
    "",
    "请在每次冷启动后，从 ``%LOCALAPPDATA%\WeMediaBaby\logs\qasync_app.log`` 复制 ``[启动耗时]`` 段落到下方对应小节。",
    "",
    "| 模式 | 环境变量 |",
    "|------|----------|",
    "| off | ``WEMEDIABABY_STARTUP_PRELOADS=off`` |",
    "| minimal | ``WEMEDIABABY_STARTUP_PRELOADS=minimal`` |",
    "| full | ``WEMEDIABABY_STARTUP_PRELOADS=full`` |",
    ""
)

foreach ($m in $modes) {
    $env:WEMEDIABABY_STARTUP_PRELOADS = $m
    $lines += "## 模式: $m"
    $lines += ""
    $lines += "```"
    $lines += "(在此粘贴 [启动耗时] 日志)"
    $lines += "```"
    $lines += ""
}

$readme = Join-Path $ReportDir "README.md"
$lines | Set-Content -Path $readme -Encoding UTF8

Write-Host "已写入模板: $readme"
Write-Host "请分别设置 WEMEDIABABY_STARTUP_PRELOADS 后运行 python main.py，并将日志中的 [启动耗时] 填入 README。"
