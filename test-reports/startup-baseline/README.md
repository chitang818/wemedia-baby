# 启动耗时基线记录

生成方式: `scripts/startup/record_startup_baseline.ps1` 或手动冷启动三次取中位数。

## 如何采集

```powershell
$env:ENABLE_STARTUP_PROFILER="1"
$env:ENABLE_PAGE_LOAD_PROFILER="1"
python main.py
```

从 `%LOCALAPPDATA%\WeMediaBaby\logs\qasync_app.log` 复制 `[启动耗时]` 段落到下表。

## 目标（普通机器）

| 指标 | 目标 |
|------|------|
| 服务初始化完成 → 主窗口 show | 首屏合计 &lt; 2.5s（优化后 &lt; 1.4s） |
| 启动后 10s 内 | 无与用户首跳叠加的重型预加载（默认 off） |

## 模式对照

| 模式 | 配置 |
|------|------|
| off | 默认；设置页「启动预加载」= 关闭 |
| minimal | `WEMEDIABABY_STARTUP_PRELOADS=minimal` 或设置页「精简」 |
| full | `WEMEDIABABY_STARTUP_PRELOADS=full` 或设置页「完整」 |

## 模式: off

```
(在此粘贴 [启动耗时] 日志)
```

## 模式: minimal

```
(在此粘贴 [启动耗时] 日志)
```

## 模式: full

```
(在此粘贴 [启动耗时] 日志)
```
