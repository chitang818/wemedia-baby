"""
团购推广占位页面
文件路径：src/ui/pages/material/group_buy_promotion_page.py
功能：团购推广功能占位页，暂未开放。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Qt

from qfluentwidgets import (
    CardWidget,
    TitleLabel,
    BodyLabel,
)

from src.ui.pages.base_page import BasePage


class GroupBuyPromotionPage(BasePage):
    """团购推广占位页面。"""

    _lazy_content = True

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("团购推广", parent)

    def _setup_content(self):
        card = CardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 32, 32, 32)
        card_layout.setSpacing(16)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = TitleLabel("团购推广", card)
        card_layout.addWidget(title)

        desc = BodyLabel(
            "本页面用于配置各平台团购商品信息，功能正在开发中，敬请期待。",
            card,
        )
        desc.setWordWrap(True)
        card_layout.addWidget(desc)

        self.content_layout.addWidget(card)
        self.content_layout.addStretch()
