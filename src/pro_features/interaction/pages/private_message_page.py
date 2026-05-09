"""
私信管理页面（Pro 功能）
文件路径：src/pro_features/interaction/pages/private_message_page.py
功能：多平台私信查看与回复（页面框架已完善，功能后期开发）
"""

from typing import Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from PySide6.QtCore import Qt

from qfluentwidgets import (
    CardWidget, SubtitleLabel, BodyLabel, CaptionLabel,
    FluentIcon, IconWidget, SearchLineEdit, ComboBox, PushButton
)

from src.ui.pages.base_page import BasePage


class PrivateMessagePage(BasePage):
    """私信管理页面 - 查看与回复各平台私信"""

    def __init__(self, parent: Optional[QWidget] = None):
        BasePage.__init__(self, "私信管理", parent)
        self._setup_content()

    def _setup_content(self):
        # 顶部说明
        desc_card = CardWidget(self)
        desc_layout = QVBoxLayout(desc_card)
        desc_layout.setSpacing(8)
        desc_layout.setContentsMargins(20, 16, 20, 16)
        title = SubtitleLabel("私信管理", desc_card)
        desc = BodyLabel(
            "集中查看抖音、视频号等平台的用户私信，支持按账号、会话筛选，并在此回复私信。"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666;")
        hint = CaptionLabel("（私信拉取与回复功能后期开发）")
        hint.setStyleSheet("color: #999;")
        desc_layout.addWidget(title)
        desc_layout.addWidget(desc)
        desc_layout.addWidget(hint)
        self.content_layout.addWidget(desc_card)

        # 筛选栏占位
        filter_card = CardWidget(self)
        filter_layout = QHBoxLayout(filter_card)
        filter_layout.setContentsMargins(16, 12, 16, 12)
        filter_layout.setSpacing(12)
        filter_layout.addWidget(SearchLineEdit(self))
        filter_layout.addWidget(ComboBox(self))
        filter_layout.addWidget(PushButton("筛选", self))
        filter_layout.addStretch()
        self.content_layout.addWidget(filter_card)

        # 会话/列表占位
        list_card = CardWidget(self)
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(24, 24, 24, 24)
        list_layout.setSpacing(12)
        list_layout.setAlignment(Qt.AlignCenter)
        icon_w = IconWidget(FluentIcon.MESSAGE)
        icon_w.setFixedSize(48, 48)
        list_layout.addWidget(icon_w, 0, Qt.AlignCenter)
        list_layout.addWidget(BodyLabel("私信会话", list_card), 0, Qt.AlignCenter)
        list_layout.addWidget(
            CaptionLabel("选择账号后，私信会话将在此展示。功能敬请期待。"),
            0, Qt.AlignCenter
        )
        self.content_layout.addWidget(list_card)
