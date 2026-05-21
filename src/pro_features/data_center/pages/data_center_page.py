"""
数据中心页面（Pro 功能）
文件路径：src/pro_features/data_center/pages/data_center_page.py
功能：数据概览与统计（页面框架已完善，功能后期开发）
"""

from typing import Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from PySide6.QtCore import Qt

from qfluentwidgets import (
    CardWidget, SubtitleLabel, BodyLabel, CaptionLabel,
    FluentIcon, IconWidget
)

from src.ui.pages.base_page import BasePage


class DataCenterPage(BasePage):
    """数据中心页面 - 数据概览与多平台统计"""

    def __init__(self, parent: Optional[QWidget] = None):
        BasePage.__init__(self, "数据中心", parent)
        self._setup_content()

    def _setup_content(self):
        # 顶部说明
        desc_card = CardWidget(self)
        desc_layout = QVBoxLayout(desc_card)
        desc_layout.setSpacing(8)
        desc_layout.setContentsMargins(20, 16, 20, 16)
        title = SubtitleLabel("数据中心", desc_card)
        desc = BodyLabel(
            "查看各平台账号的播放量、粉丝、作品等数据概览。支持按账号、时间范围筛选。"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666;")
        hint = CaptionLabel("（数据拉取与图表功能后期开发）")
        hint.setStyleSheet("color: #999;")
        desc_layout.addWidget(title)
        desc_layout.addWidget(desc)
        desc_layout.addWidget(hint)
        self.content_layout.addWidget(desc_card)

        # 占位统计卡片
        cards_info = [
            ("播放量统计", FluentIcon.PLAY, "总播放量、昨日播放、趋势", "--"),
            ("粉丝数据", FluentIcon.PEOPLE, "粉丝总数、涨粉、掉粉", "--"),
            ("作品数据", FluentIcon.VIDEO, "作品数、点赞、评论、分享", "--"),
            ("互动概览", FluentIcon.CHAT, "评论、私信、@ 提及", "--"),
        ]
        for tit, icon, sub, val in cards_info:
            card = CardWidget(self)
            card.setMinimumHeight(100)
            lay = QVBoxLayout(card)
            lay.setContentsMargins(16, 12, 16, 12)
            lay.setSpacing(6)
            row = QHBoxLayout()
            icon_w = IconWidget(icon)
            icon_w.setFixedSize(28, 28)
            row.addWidget(icon_w)
            row.addWidget(SubtitleLabel(tit, card))
            row.addStretch()
            lay.addLayout(row)
            lay.addWidget(BodyLabel(sub, card))
            lay.addWidget(CaptionLabel(val, card))
            self.content_layout.addWidget(card)

        # 底部占位提示
        footer_card = CardWidget(self)
        footer_layout = QVBoxLayout(footer_card)
        footer_layout.setContentsMargins(20, 16, 20, 16)
        footer_layout.setAlignment(Qt.AlignCenter)
        footer_label = CaptionLabel("选择账号与时间范围后，将在此展示数据图表。功能敬请期待。")
        footer_label.setStyleSheet("color: #999;")
        footer_layout.addWidget(footer_label)
        self.content_layout.addWidget(footer_card)
