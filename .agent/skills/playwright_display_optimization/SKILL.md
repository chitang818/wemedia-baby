---
name: playwright_display_optimization
description: Playwright 浏览器显示优化与持久化最佳实践 (解决白边、窗口最大化、Session持久化)
---

# Playwright 浏览器显示优化与持久化指南

本技能文档总结了在 `Playwright` 自动化开发中，如何彻底解决浏览器窗口**右侧白边**、**无法最大化**以及**Session 丢失**的问题。

## 核心问题 (Problem Statement)

在使用 Playwright (特别是 `chromium`) 时，常遇到以下痛点：

1.  **右侧/底部白边**：即使窗口最大化，网页内容仍被裁剪在 1280x720 或其他固定分辨率内。
2.  **非真实全屏**：`--start-maximized` 参数无效，或者窗口边框即使拉大，内容区也不跟随。
3.  **DPI 缩放异常**：在 125% 或 150% 缩放的屏幕上，浏览器 UI 异常。
4.  **状态丢失**：每次启动都需要重新登录，Cookie 无法自动保存到本地 Chrome 目录。

## 解决方案 (Best Practices)

### 1. 架构选择：Persistent Context

**弃用** `browser.new_context()`，**改用** `launch_persistent_context`。

- **Rationale**: `new_context` 是为测试设计的“一次性环境”，天生倾向于隔离和重置。`launch_persistent_context` 直接加载用户数据目录 (`User Data Dir`)，行为更像真实用户打开浏览器。

### 2. 关键代码配置

在启动浏览器时，必须组合使用以下参数才能达成完美效果：

```python
# 1. 获取用户数据目录 (确保环境持久化)
user_data_dir = os.path.join(app_data_path, "user_data")

# 2. 启动参数 (Args)
args = [
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled", # 基础抗检测
    "--start-maximized",                             # 核心：启动时让窗口最大化
]

# 3. 启动选项 (Launch Options)
launch_options = {
    "user_data_dir": user_data_dir,
    "headless": False,
    "channel": "chrome",            # 强烈建议：使用本地安装的 Chrome
    "args": args,

    # --- 核心修复配置 START ---
    "viewport": None,               # 1. 告诉 Playwright 不要强行设置视口大小
    "no_viewport": True,            # 2. 【关键】显式禁用视口模拟，防止默认的 1280x720 限制
    # "device_scale_factor": 1.0,   # 3. 【关键】不要设置此项，移除后让浏览器自动跟随系统 DPI
    # --- 核心修复配置 END ---

    "ignore_https_errors": True,
}

# 4. 启动
context = await playwright.chromium.launch_persistent_context(**launch_options)
```

### 3. 参数详解

| 参数                  | 值           | 作用                                                                                                                              |
| :-------------------- | :----------- | :-------------------------------------------------------------------------------------------------------------------------------- |
| `viewport`            | `None`       | 取消 Python 侧对视口对象的定义。                                                                                                  |
| `no_viewport`         | `True`       | **这是必杀技**。显式通知底层 CDP 协议禁用视口模拟。如果缺少此项，Playwright 仍可能默认应用 800x600 或 1280x720 限制，导致白边。   |
| `--start-maximized`   | (在 args 中) | 让浏览器窗口以 Windows 最大化状态启动（点击了最大化按钮的效果）。                                                                 |
| `device_scale_factor` | **(移除)**   | 移除此键值。如果强制设为 1.0，在高分屏（如 Surface 或 4K 屏）上会导致页面看起来很小或布局错乱。移除后由 Chrome 自行适配系统设置。 |

## 常见误区 (Common Pitfalls)

1.  **误区一**：只设置了 `--start-maximized` 但没设置 `no_viewport=True`。
    - _结果_：窗口确实最大化了，但网页内容只渲染在左上角一小块区域，右下角全是空白。
2.  **误区二**：在 `launch_persistent_context` 中混用 `new_context` 的参数。
    - _注意_：Persistent 模式下，`context` 就是浏览器本身，没有 `browser` 对象这一层级，不要尝试再去 verify `browser.version` 等属性。

## 适用场景

- **RPA 自动化**：需要模拟真实用户操作，且长期保存登录态。
- **爬虫**：需要最大化窗口以加载完整 DOM 结构，或应对反爬虫指纹检测（全屏属于真实用户特征）。
- **UI 测试**：需要在真实渲染尺寸下验证布局。
