"""
个人中心页面（开源包装层）

闭源版真实实现：`src/proprietary/ui/personal_center_page.py`
开源版：若缺失闭源目录，则提供占位页面（不会崩溃）。\n
注意：`PageFactory` 仍会引用本文件的 `PersonalCenterPage`。\n
"""

from __future__ import annotations

from typing import Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout

from .base_page import BasePage


try:
    from src.proprietary.ui.personal_center_page import PersonalCenterPage as _ImplPersonalCenterPage
    PersonalCenterPage = _ImplPersonalCenterPage
except Exception:
    class PersonalCenterPage(BasePage):  # type: ignore[no-redef]
        _lazy_content = True

        def __init__(self, parent: Optional[QWidget] = None):
            super().__init__("个人中心", parent)

        def _setup_content(self):
            layout = QVBoxLayout()
            self.content_layout.addLayout(layout)
            try:
                from qfluentwidgets import BodyLabel
                layout.addWidget(BodyLabel("当前为开源版：不包含个人中心与订阅权益功能。", self))
            except Exception:
                pass
            self.content_layout.addStretch()
