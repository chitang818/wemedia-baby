@echo off
chcp 65001 >nul
title 媒小宝 - 同步公开开源仓库
cd /d "%~dp0..\.."

echo.
echo ========================================
echo   同步到公开仓 wemedia-baby（仅开源部分）
echo   请先确保 main 已提交且无未保存改动
echo ========================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0publish_oss_to_public.ps1"
set EXITCODE=%ERRORLEVEL%

echo.
if %EXITCODE% neq 0 (
    echo [失败] 同步未成功，请查看上方提示。
) else (
    echo [成功] 可到 GitHub 打开 wemedia-baby 核对。
)
echo.
pause
exit /b %EXITCODE%
