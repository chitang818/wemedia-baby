# 媒小宝项目清理工具
# 用途：清理构建产物和打包缓存 (Nuitka & PyInstaller)

$ErrorActionPreference = "Continue"

Write-Host "====================================="
Write-Host "     媒小宝项目清理工具 v2.0    "
Write-Host "====================================="
Write-Host ""
Write-Host "本工具将清理以下内容：" -ForegroundColor Yellow
Write-Host "  - 构建/发布目录 (Nuitka & PyInstaller 构建产物)"
Write-Host "  - Nuitka 缓存 (*.build, *.dist, *.onefile-build)"
Write-Host "  - Python 缓存 (__pycache__, *.pyc, *.pyo)"
Write-Host "  - 测试缓存 (.pytest_cache, .mypy_cache, .tox)"
Write-Host "  - 日志文件 (logs/*.log)"
Write-Host ""
Write-Host "源代码不会受到影响。" -ForegroundColor Green
Write-Host ""

$msg = "确认执行清理？(Y/N)"
$confirmation = Read-Host $msg

if ($confirmation -eq "Y" -or $confirmation -eq "y") {
    Write-Host ""
    Write-Host "正在执行清理..." -ForegroundColor Cyan
    Write-Host "-------------------------------------"

    # 0. 终止占用进程
    Write-Host "[0/6] 正在检查运行中的进程..." -ForegroundColor White
    $processesToKill = @("WeMediaBaby", "QtWebEngineProcess", "main")
    foreach ($procName in $processesToKill) {
        $procs = Get-Process -Name $procName -ErrorAction SilentlyContinue
        if ($procs) {
            Write-Host "  - 正在终止进程: $procName" -ForegroundColor Yellow
            Stop-Process -Name $procName -Force -ErrorAction SilentlyContinue
        }
    }
    # 等待进程完全释放文件锁
    Start-Sleep -Seconds 2

    # 1. 清理基础目录
    Write-Host "[1/6] 正在清理构建目录 (Nuitka & PyInstaller)..." -ForegroundColor White
    $basicTargets = @("build", "dist", "docs_backup")
    foreach ($t in $basicTargets) {
        if (Test-Path $t) {
            Write-Host "  - 正在删除: $t" -ForegroundColor Gray
            Remove-Item -Path $t -Recurse -Force -ErrorAction Continue

            # 二次检查（处理文件占用的情况）
            if (Test-Path $t) {
                Write-Host "    - 警告: $t 无法完全删除，正在重试..." -ForegroundColor Yellow
                Start-Sleep -Seconds 1
                Remove-Item -Path $t -Recurse -Force -ErrorAction Continue
            }
        }
    }

    # 2. 清理 Nuitka 打包缓存
    Write-Host "[2/6] 正在清理 Nuitka 打包缓存..." -ForegroundColor White
    # Nuitka 生成的缓存目录模式: main.build, main.dist, main.onefile-build
    $nuitkaPatterns = @("*.build", "*.dist", "*.onefile-build")
    foreach ($pattern in $nuitkaPatterns) {
        Get-ChildItem -Path . -Directory -Filter $pattern -ErrorAction SilentlyContinue | ForEach-Object {
            Write-Host "  - 正在删除: $($_.Name)" -ForegroundColor Gray
            Remove-Item -Path $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    # 清理 nuitka-crash-report.xml
    if (Test-Path "nuitka-crash-report.xml") {
        Write-Host "  - 正在删除: nuitka-crash-report.xml" -ForegroundColor Gray
        Remove-Item -Path "nuitka-crash-report.xml" -Force -ErrorAction SilentlyContinue
    }

    # 清理 PyInstaller 可能生成的临时 spec 文件（保留 main.spec）
    Get-ChildItem -Path . -Filter "*.spec" -File -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.Name -ne "main.spec") {
            Write-Host "  - 正在删除临时 spec 文件: $($_.Name)" -ForegroundColor Gray
            Remove-Item -Path $_.FullName -Force -ErrorAction SilentlyContinue
        }
    }

    # 3. 清理 Python 缓存
    Write-Host "[3/6] 正在清理 Python 缓存..." -ForegroundColor White
    # 清理 __pycache__ 目录
    $pycacheCount = 0
    Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue | ForEach-Object {
        Remove-Item -Path $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        $pycacheCount++
    }
    Write-Host "  - 已删除 $pycacheCount 个 __pycache__ 目录" -ForegroundColor Gray

    # 清理 .pyc 和 .pyo 文件
    $pycFiles = Get-ChildItem -Path . -Recurse -Include "*.pyc", "*.pyo" -File -ErrorAction SilentlyContinue
    if ($pycFiles) {
        $pycFiles | Remove-Item -Force -ErrorAction SilentlyContinue
        Write-Host "  - 已删除 $($pycFiles.Count) 个 .pyc/.pyo 文件" -ForegroundColor Gray
    }

    # 清理 egg-info 目录
    Get-ChildItem -Path . -Recurse -Directory -Filter "*.egg-info" -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host "  - 正在删除: $($_.Name)" -ForegroundColor Gray
        Remove-Item -Path $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }

    # 4. 清理测试和类型检查缓存
    Write-Host "[4/6] 正在清理测试/类型检查缓存..." -ForegroundColor White
    $testCacheTargets = @(".pytest_cache", ".mypy_cache", ".tox", ".hypothesis")
    foreach ($t in $testCacheTargets) {
        if (Test-Path $t) {
            Write-Host "  - 正在删除: $t" -ForegroundColor Gray
            Remove-Item -Path $t -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    # 5. 清理覆盖率报告
    Write-Host "[5/6] 正在清理覆盖率报告..." -ForegroundColor White
    $coverageTargets = @(".coverage", "htmlcov", "coverage.xml")
    foreach ($t in $coverageTargets) {
        if (Test-Path $t) {
            Write-Host "  - 正在删除: $t" -ForegroundColor Gray
            Remove-Item -Path $t -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    # 6. 清理日志文件
    Write-Host "[6/6] 正在清理日志文件..." -ForegroundColor White
    if (Test-Path "logs") {
        $logFiles = Get-ChildItem -Path "logs" -Filter "*.log" -ErrorAction SilentlyContinue
        if ($logFiles) {
            $logFiles | Remove-Item -Force -ErrorAction SilentlyContinue
            Write-Host "  - 已删除 $($logFiles.Count) 个日志文件" -ForegroundColor Gray
        }
    }

    Write-Host "-------------------------------------"
    Write-Host ""
    Write-Host "清理完成!" -ForegroundColor Green
}
else {
    Write-Host ""
    Write-Host "操作已取消。" -ForegroundColor Yellow
}

Write-Host "====================================="
pause

