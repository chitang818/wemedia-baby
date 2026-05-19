"""
公告栏组件
文件路径：src/ui/components/announcement_widget.py
功能：工作台公告栏，显示版本信息、更新日志、使用提示等，自动适配深色/浅色主题
"""

from typing import List, Dict, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from qfluentwidgets import (
    CardWidget, BodyLabel, CaptionLabel, SubtitleLabel,
    FluentIcon, IconWidget, isDarkTheme
)


DEFAULT_ANNOUNCEMENTS = [
    {
        "icon": FluentIcon.MEGAPHONE,
        "title": "公测公告",
        "content": "软件内测期间，注册账号并关注公众号发送用户名，登记成功后免费使用所有软件功能！！！",
        "content_color_light": "#FF4D4F",
        "content_color_dark": "#FF7875",
        "color": "#0078D4",
    },
    {
        "icon": FluentIcon.VIDEO,
        "title": "平台与插件说明",
        "content": "软件内测期间支持插件有限，目前抖音、快手、视频号三个平台的视频发布已经可以使用，其他平台及图文发布还在完善中……",
        "color": "#138496",
    },
]

_52POJIE_ANNOUNCEMENTS = [
    {
        "icon": FluentIcon.MEGAPHONE,
        "title": "欢迎使用",
        "content": "媒小宝-吾爱破解论坛特别版，已解锁全部功能，无需登录即可使用。",
        "color": "#0078D4",
    },
    {
        "icon": FluentIcon.VIDEO,
        "title": "平台与插件说明",
        "content": "目前抖音、快手、视频号三个平台的视频发布已经可以使用，其他平台及图文发布还在完善中……",
        "color": "#138496",
    },
]


class AnnouncementItem(QWidget):
    """单条公告"""

    def __init__(
        self,
        icon,
        title: str,
        content: str,
        color: str = "#0078D4",
        content_color: str = "",
        parent=None,
    ):
        super().__init__(parent)
        dark = isDarkTheme()

        if not content_color:
            content_color = "#AAAAAA" if dark else "#757575"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        icon_bg = QWidget(self)
        icon_bg.setFixedSize(28, 28)
        icon_bg.setStyleSheet(
            f"background-color: {color}18; border-radius: 14px;"
        )
        icon_layout = QVBoxLayout(icon_bg)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_w = IconWidget(icon, icon_bg)
        icon_w.setFixedSize(14, 14)
        icon_layout.addWidget(icon_w, 0, Qt.AlignCenter)
        layout.addWidget(icon_bg)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(1)
        text_layout.setContentsMargins(0, 0, 0, 0)

        title_color = "#E0E0E0" if dark else "#1A1A1A"
        title_label = BodyLabel(title, self)
        title_label.setStyleSheet(f"font-weight: 600; font-size: 14px; color: {title_color};")

        content_label = CaptionLabel(content, self)
        content_label.setStyleSheet(f"color: {content_color}; font-size: 13px;")
        content_label.setWordWrap(True)

        text_layout.addWidget(title_label)
        text_layout.addWidget(content_label)
        layout.addLayout(text_layout, 1)


class AnnouncementWidget(CardWidget):
    """公告栏组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        from config.feature_flags import FeatureFlags
        announcements = _52POJIE_ANNOUNCEMENTS if FeatureFlags.is_52pojie() else DEFAULT_ANNOUNCEMENTS
        self.set_announcements(announcements)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(0)

        dark = isDarkTheme()
        title_color = "#FFFFFF" if dark else "#1A1A1A"
        self.title_label = SubtitleLabel("公告栏", self)
        self.title_label.setStyleSheet(f"font-weight: 600; font-size: 16px; color: {title_color};")
        layout.addWidget(self.title_label)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )

        self.list_container = QWidget(self)
        self.list_container.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 4, 0, 0)
        self.list_layout.setSpacing(2)
        self.scroll_area.setWidget(self.list_container)

        layout.addWidget(self.scroll_area, 1)

    def set_announcements(self, items: List[Dict]):
        dark = isDarkTheme()

        while self.list_layout.count():
            child = self.list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for item in items:
            cc = ""
            if dark and item.get("content_color_dark"):
                cc = item["content_color_dark"]
            elif not dark and item.get("content_color_light"):
                cc = item["content_color_light"]
            elif item.get("content_color"):
                cc = item["content_color"]

            widget = AnnouncementItem(
                icon=item.get("icon", FluentIcon.INFO),
                title=item.get("title", ""),
                content=item.get("content", ""),
                color=item.get("color", "#0078D4"),
                content_color=cc,
                parent=self.list_container,
            )
            self.list_layout.addWidget(widget)

        self.list_layout.addStretch()
