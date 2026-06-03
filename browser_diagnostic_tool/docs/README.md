# 浏览器环境诊断工具

这个目录是独立诊断工具，不直接修改媒小宝主业务代码。

## 目标

对照三种环境：

- `local_manual`：本地 Chrome 手动发布。
- `wmb_manual`：媒小宝打开的 Chrome 中手动发布。
- `wmb_auto`：媒小宝自动发布流程。

诊断结果用于分析浏览器环境差异和风险线索，不用于规避平台检测。

## Chrome 扩展安装

1. 打开 Chrome 扩展管理页。
2. 开启开发者模式。
3. 选择“加载已解压的扩展程序”。
4. 选择 `browser_diagnostic_tool/extension`。

## 采集方式

在目标平台页面点击扩展图标，选择平台、模式、阶段，然后点击采集按钮。扩展会下载一个 JSON 文件。

扩展只读采集，不保存 cookie value，不修改页面，不自动提交。

## 生成报告

示例：

```powershell
python -m browser_diagnostic_tool.desktop.build_report `
  --platform xiaohongshu `
  --test-run-id test001 `
  --snapshot C:\path\local_manual.json `
  --snapshot C:\path\wmb_manual.json `
  --snapshot C:\path\wmb_auto.json
```

报告默认输出到：

`%LOCALAPPDATA%\WeMediaBaby\debug\browser_diagnostics\<platform>\<YYYYMMDD>\<test_run_id>\`

## 注意

- 本地 Chrome 基线不要用 Playwright、远程调试端口或 CDP 接管。
- 建议使用专用测试账号。
- 扩展本身会改变环境，报告会标记 `extension_present=true`。

