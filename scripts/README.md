# scripts/ 目录说明（整理后）

目标：脚本按用途分组，入口命名清晰；旧路径尽量保留“转发”以兼容历史用法。

## build/（打包构建）
- `build/build.bat`：交互式构建菜单入口（Fast/Secure + DistMode）
- `build/build_fast.ps1`：PyInstaller 快速构建
- `build/build_nuitka.ps1`：Nuitka 正式构建

## release/（发版）
- `release/build_release_matrix.ps1`：按需选择构建 DistMode（可多选，支持 DryRun）
- `release/update_version.py`：更新版本号
- `release/RELEASE_STEPS.md`：发版步骤

## test/（测试）
- `test/run_tests.py`：pytest 一键入口（单元/集成/全量、覆盖率、HTML 报告）
- `test/run_tests.bat`：Windows 友好入口（调用 run_tests.py）
- `test/ui_smoke_main_window.py`：UI 冒烟（可用于 CI）

## maintenance/（维护/清理）
- `maintenance/factory_reset.py` / `maintenance/factory_reset.ps1`：出厂重置
- `maintenance/clear_database.ps1`：清空数据库（谨慎）
- `maintenance/clean_project.ps1`：清理构建产物与缓存
- `maintenance/clean_orphans.py`：清理孤儿文案记录

## dev/（开发工具）
- `dev/download_platform_icons.py`：下载平台图标（Simple Icons）

