---
name: fluent_ui_dev
description: 界面UI开发专家指南。当用户要求修改界面UI、调整布局、新增组件或优化视觉效果时，必须调用此技能。基于结合。
---

# Fluent UI 开发技能

## 适用场景 (何时调用)

**当用户的请求包含以下意图时，必须激活此技能：**

- "修改界面" / "调整UI"
- "优化布局" / "界面排版"
- "新增按钮" / "新增输入框" / "新增组件"
- "美化界面" / "更现代的设计"
- 任何涉及到 `src/ui` 目录下文件的修改请求。

## 概述

本技能提供了在 `wemedia-baby` 项目中创建和修改 UI 组件的指南。本项目使用 `PySide6-Fluent-Widgets` 来实现 Fluent Design System（Windows 11 风格）。

## 前置条件

- **库**: `PySide6-Fluent-Widgets` (导入名为 `qfluentwidgets`)。
- **设计参考**: [PyQt-Fluent-Widgets GitHub](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)。
- **文档**: [PyQt-Fluent-Widgets 文档](https://qfluentwidgets.com/)。

## 核心规则

1.  **使用优先级**: 只要存在 Fluent 等效组件，**必须** 使用 `qfluentwidgets` 组件，而不是原生的 `PySide6.QtWidgets`。
    - 示例: 使用 `PushButton` (来自 `qfluentwidgets`) 而不是 `QPushButton`。
    - 示例: 使用 `LineEdit` (来自 `qfluentwidgets`) 而不是 `QLineEdit`。
2.  **实现细节**:
    - 虽然设计参考是 "PyQt-Fluent-Widgets"，但安装的库是 **PySide6-Fluent-Widgets**。
    - 必须从 `qfluentwidgets` 导入 (例如: `from qfluentwidgets import PushButton`)。
    - **禁止** 从 `PyQt5` 或 `PyQt6` 导入。**只能使用 `PySide6`**。
3.  **缺失功能**:
    - **关键**: 如果 `PyQt-Fluent-Widgets` 库中没有所需的 UI 功能或组件，**不要** 尝试自己拼凑解决方案或立即使用标准 Qt 控件。
    - **行动**: 你 **必须** 告知用户 UI 库中缺少该功能，并询问下一步指示。

## 常用模式

### 1. 基础窗口

使用 `FluentWindow` 作为主窗口的基类。

```python
from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentWindow

class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("我的应用")
```

### 2. 通知提醒

使用 `InfoBar` 进行应用内通知。

```python
from PySide6.QtCore import Qt
from qfluentwidgets import InfoBar, InfoBarPosition

InfoBar.success(
    title='成功',
    content='操作已成功完成',
    orient=Qt.Horizontal,
    isClosable=True,
    position=InfoBarPosition.TOP_RIGHT,
    duration=2000,
    parent=self
)
```

### 3. 状态提示

使用 `StateToolTip` 进行非打扰式的状态更新（类似吐司消息）。

```python
from qfluentwidgets import StateToolTip

StateToolTip(
    title="就绪",
    content="系统已准备就绪",
    parent=self
).show()
```

## 故障排除

- **DirectComposition 错误**: 如果在 Windows 上看到与 DirectComposition 相关的错误，通常是底层 Chromium/QtWebEngine（如果使用了）或 Qt 渲染引擎的无害警告。通常可以通过环境变量忽略或抑制它们。
- **导入错误**: 确保安装的是 `PySide6-Fluent-Widgets`，而 **不是** `PyQt-Fluent-Widgets`。
