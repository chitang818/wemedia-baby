@echo off
cd /d "%~dp0..\.."
setlocal

echo.
echo  ==================================================
echo.
echo            媒 小 宝 版 本 管 理 v2.0
echo.
echo  ==================================================
echo.
echo    [1] 补丁更新 - 修复Bug     - 1.0.0 到 1.0.1
echo    [2] 功能更新 - 增加新功能  - 1.0.0 到 1.1.0
echo    [3] 大版本   - 重大架构变更 - 1.0.0 到 2.0.0
echo.
echo  ==================================================
echo.
set /p choice="  请选择 [1/2/3]: "

if "%choice%"=="1" goto patch
if "%choice%"=="2" goto minor
if "%choice%"=="3" goto major
echo.
echo  无效输入，请重新运行。
goto end

:patch
echo.
echo  正在执行补丁更新...
python scripts\release\update_version.py patch
goto end

:minor
echo.
echo  正在执行功能更新...
python scripts\release\update_version.py minor
goto end

:major
echo.
echo  正在执行大版本更新...
python scripts\release\update_version.py major
goto end

:end
echo.
pause
