"""
可折叠公告面板（工作台 KPI 下方、快捷操作上方，默认展开）
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent

from qfluentwidgets import CardWidget, SubtitleLabel, TransparentToolButton, FluentIcon, isDarkTheme

from src.ui.components.announcement_widget import AnnouncementWidget


class _AnnouncementHeaderBar(QWidget):
    clicked = Signal()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class CollapsibleAnnouncementPanel(CardWidget):
    """标题栏可点击展开/收起的公告容器。"""

    HEADER_HEIGHT = 34

    def __init__(self, parent: Optional[QWidget] = None, *, collapsed: bool = False):
        super().__init__(parent)
        self._collapsed = collapsed

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 2, 14, 10)
        root.setSpacing(6)

        header = _AnnouncementHeaderBar(self)
        header.setFixedHeight(self.HEADER_HEIGHT)
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)

        self._title = SubtitleLabel("公告", header)
        dark = isDarkTheme()
        self._title.setStyleSheet(
            f"font-weight: 600; font-size: 15px; color: {'#FFF' if dark else '#1A1A1A'};"
        )
        hl.addWidget(self._title)
        hl.addStretch(1)

        _chev_down = getattr(FluentIcon, "CHEVRON_DOWN_MED", FluentIcon.DOWN)
        self._toggle_btn = TransparentToolButton(_chev_down, header)
        self._toggle_btn.setFixedSize(28, 28)
        self._toggle_btn.clicked.connect(self.toggle_collapsed)
        hl.addWidget(self._toggle_btn)

        header.clicked.connect(self.toggle_collapsed)
        root.addWidget(header)

        self._content = AnnouncementWidget(self, show_header=False, compact=True)
        self._content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        root.addWidget(self._content)

        self._apply_collapsed_state()

    @property
    def is_collapsed(self) -> bool:
        return self._collapsed

    def toggle_collapsed(self) -> None:
        self._collapsed = not self._collapsed
        self._apply_collapsed_state()

    def _content_height(self) -> int:
        try:
            return int(self._content.preferred_content_height())
        except Exception:
            return 80

    def _apply_collapsed_state(self) -> None:
        h = self._content_height()
        self._content.setMaximumHeight(h)
        self._content.setVisible(not self._collapsed)
        if self._collapsed:
            icon = getattr(FluentIcon, "CHEVRON_DOWN_MED", FluentIcon.DOWN)
        else:
            icon = getattr(FluentIcon, "CHEVRON_UP_MED", FluentIcon.UP)
        self._toggle_btn.setIcon(icon)
        if self._collapsed:
            self.setMaximumHeight(self.HEADER_HEIGHT + 8)
        else:
            self.setMaximumHeight(self.HEADER_HEIGHT + self._content_height() + 20)
