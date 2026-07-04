"""
公告栏组件
文件路径：src/ui/components/announcement_widget.py
功能：工作台公告栏，显示版本信息、更新日志、使用提示等，自动适配深色/浅色主题
"""

from typing import List, Dict, Optional

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSizePolicy,
    QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics

from qfluentwidgets import (
    CardWidget,
    BodyLabel,
    CaptionLabel,
    SubtitleLabel,
    FluentIcon,
    IconWidget,
    isDarkTheme,
)
from src.ui.components.workspace_scroll_area import (
    create_workspace_scroll_area,
    set_workspace_scroll_content,
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
        "content": "软件内测期间支持插件有限，目前抖音、快手、视频号这三个平台的视频和图文发布已经可以使用，其他平台及功能逐步在完善中……",
        "content_color_light": "#FF4D4F",
        "content_color_dark": "#FF7875",
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
        "content": "软件内测期间支持插件有限，目前抖音、快手、视频号这三个平台的视频和图文发布已经可以使用，其他平台及功能逐步在完善中……",
        "content_color_light": "#FF4D4F",
        "content_color_dark": "#FF7875",
        "color": "#138496",
    },
]

_COMPACT_ROW_HEIGHT = 36
_COMPACT_DIVIDER_HEIGHT = 1


class AnnouncementItem(QWidget):
    """单条公告（紧凑模式为单行展示）"""

    def __init__(
        self,
        icon,
        title: str,
        content: str,
        color: str = "#0078D4",
        content_color: str = "",
        parent=None,
        *,
        compact: bool = False,
    ):
        super().__init__(parent)
        self._compact = compact
        self._title_text = title
        self._content_text = content
        self._content_color = content_color
        self._accent_color = color

        dark = isDarkTheme()
        if not self._content_color:
            self._content_color = "#AAAAAA" if dark else "#757575"

        if compact:
            self._build_compact_row(icon)
        else:
            self._build_expanded_row(icon)

    def _build_compact_row(self, icon) -> None:
        dark = isDarkTheme()
        self.setFixedHeight(_COMPACT_ROW_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(10)

        icon_px = 22
        icon_bg = QWidget(self)
        icon_bg.setFixedSize(icon_px, icon_px)
        icon_bg.setStyleSheet(
            f"background-color: {self._accent_color}22; border-radius: {icon_px // 2}px;"
        )
        icon_layout = QVBoxLayout(icon_bg)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_w = IconWidget(icon, icon_bg)
        icon_w.setFixedSize(12, 12)
        icon_layout.addWidget(icon_w, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_bg, 0, Qt.AlignmentFlag.AlignVCenter)

        title_color = "#E8E8E8" if dark else "#1A1A1A"
        self._title_label = BodyLabel(self._title_text, self)
        self._title_label.setStyleSheet(
            f"font-weight: 600; font-size: 13px; color: {title_color};"
        )
        self._title_label.setWordWrap(False)
        self._title_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._title_label, 0, Qt.AlignmentFlag.AlignVCenter)

        sep = BodyLabel("·", self)
        sep.setStyleSheet(
            f"font-size: 13px; color: {'#666' if dark else '#B0B0B0'}; padding: 0 2px;"
        )
        sep.setFixedWidth(12)
        sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sep, 0, Qt.AlignmentFlag.AlignVCenter)

        self._content_label = CaptionLabel(self._content_text, self)
        self._content_label.setStyleSheet(
            f"color: {self._content_color}; font-size: 12px;"
        )
        self._content_label.setWordWrap(False)
        self._content_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._content_label, 1, Qt.AlignmentFlag.AlignVCenter)

    @staticmethod
    def _make_divider(parent: QWidget) -> QFrame:
        dark = isDarkTheme()
        line = QFrame(parent)
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        divider = "#FFFFFF14" if dark else "#0000000D"
        line.setStyleSheet(f"background: {divider}; border: none; max-height: 1px;")
        return line

    def _build_expanded_row(self, icon) -> None:
        dark = isDarkTheme()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)

        icon_px = 28
        icon_bg = QWidget(self)
        icon_bg.setFixedSize(icon_px, icon_px)
        icon_bg.setStyleSheet(
            f"background-color: {self._accent_color}18; border-radius: {icon_px // 2}px;"
        )
        icon_layout = QVBoxLayout(icon_bg)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_w = IconWidget(icon, icon_bg)
        icon_w.setFixedSize(14, 14)
        icon_layout.addWidget(icon_w, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_bg, 0, Qt.AlignmentFlag.AlignTop)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.setContentsMargins(0, 0, 0, 0)

        title_color = "#E0E0E0" if dark else "#1A1A1A"
        title_label = BodyLabel(self._title_text, self)
        title_label.setStyleSheet(
            f"font-weight: 600; font-size: 14px; color: {title_color};"
        )
        content_label = CaptionLabel(self._content_text, self)
        content_label.setStyleSheet(f"color: {self._content_color}; font-size: 13px;")
        content_label.setWordWrap(True)

        text_layout.addWidget(title_label)
        text_layout.addWidget(content_label)
        layout.addLayout(text_layout, 1)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._compact:
            return
        label = getattr(self, "_content_label", None)
        if label is None:
            return
        metrics = QFontMetrics(label.font())
        available = max(40, label.width() - 4)
        label.setText(metrics.elidedText(self._content_text, Qt.TextElideMode.ElideRight, available))


class AnnouncementWidget(CardWidget):
    """公告栏组件"""

    def __init__(
        self,
        parent=None,
        *,
        show_header: bool = True,
        compact: bool = False,
    ):
        super().__init__(parent)
        self._show_header = show_header
        self._compact = compact
        self._item_widgets: List[AnnouncementItem] = []
        self._current_announcements = []
        self._init_ui()
        from config.feature_flags import FeatureFlags

        announcements = _52POJIE_ANNOUNCEMENTS if FeatureFlags.is_52pojie() else DEFAULT_ANNOUNCEMENTS
        self.set_announcements(announcements)
        
        from qfluentwidgets import qconfig
        qconfig.themeChanged.connect(self._on_theme_changed)

    def _on_theme_changed(self):
        """响应主题切换"""
        if self._show_header and hasattr(self, 'title_label'):
            dark = isDarkTheme()
            title_color = "#FFFFFF" if dark else "#1A1A1A"
            self.title_label.setStyleSheet(
                f"font-weight: 600; font-size: 16px; color: {title_color};"
            )
        if self._current_announcements:
            self.set_announcements(self._current_announcements)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        embedded_compact = self._compact and not self._show_header
        if embedded_compact:
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self.setStyleSheet("AnnouncementWidget{background:transparent;border:none;}")
        elif self._compact:
            layout.setContentsMargins(4, 2, 4, 4)
            layout.setSpacing(0)
        else:
            layout.setContentsMargins(12, 10, 12, 10)
            layout.setSpacing(0)

        if self._show_header:
            dark = isDarkTheme()
            title_color = "#FFFFFF" if dark else "#1A1A1A"
            self.title_label = SubtitleLabel("公告栏", self)
            self.title_label.setStyleSheet(
                f"font-weight: 600; font-size: 16px; color: {title_color};"
            )
            layout.addWidget(self.title_label)

        self.scroll_area = create_workspace_scroll_area(self)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        self.list_container = QWidget(self)
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(0)
        set_workspace_scroll_content(self.scroll_area, self.list_container)

        layout.addWidget(self.scroll_area)

    def preferred_content_height(self) -> int:
        """紧凑列表所需高度（供外层折叠面板使用）。"""
        count = len(self._item_widgets)
        if count <= 0:
            return 0
        if self._compact:
            dividers = max(0, count - 1) * _COMPACT_DIVIDER_HEIGHT
            return count * _COMPACT_ROW_HEIGHT + dividers
        return min(200, count * 72)

    def set_announcements(self, items: List[Dict]) -> None:
        self._current_announcements = items
        dark = isDarkTheme()
        self._item_widgets.clear()

        while self.list_layout.count():
            child = self.list_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

        for index, item in enumerate(items):
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
                compact=self._compact,
            )
            self._item_widgets.append(widget)
            self.list_layout.addWidget(widget)
            if self._compact and index < len(items) - 1:
                self.list_layout.addWidget(AnnouncementItem._make_divider(self.list_container))

        content_h = self.preferred_content_height()
        if self._compact:
            self.scroll_area.setMaximumHeight(content_h)
        else:
            self.scroll_area.setMaximumHeight(min(200, content_h))
