@echo off
chcp 65001 >nul
echo.
echo ==========================================
echo   媒小宝 - 一键测试脚本（Windows）
echo ==========================================
echo.
echo 用法:
echo   run_tests.bat                   全量测试
echo   run_tests.bat unit              仅单元测试
echo   run_tests.bat integration       仅集成测试
echo   run_tests.bat --quick           快速模式
echo   run_tests.bat --open            测试后打开报告
echo.

cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请确认已安装 Python 并加入 PATH
    pause
    exit /b 1
)

python test\run_tests.py %*

set EXIT_CODE=%errorlevel%

echo.
if %EXIT_CODE% equ 0 (
    echo 所有测试通过！软件功能一切正常。
) else (
    echo 测试未全部通过，请查看上方输出或报告文件。
)

echo.
echo ==========================================
echo   报告文件位置（双击可在浏览器中打开）：
echo   test-reports\summary.html     通俗易懂版报告
echo   test-reports\report.html      技术详情版报告
echo ==========================================
echo.
echo 按任意键退出...
pause >nul

exit /b %EXIT_CODE%
