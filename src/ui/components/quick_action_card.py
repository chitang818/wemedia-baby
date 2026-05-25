"""
快速操作卡片组件
文件路径：src/ui/components/quick_action_card.py
功能：显示主要操作的可点击卡片，包含大图标、标题和描述，支持悬浮效果与深色主题
"""

from typing import Optional

from PySide6.QtWidgets import QWidget, QVBoxLayout, QGraphicsDropShadowEffect, QSizePolicy
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor, QColor, QEnterEvent

from qfluentwidgets import (
    CardWidget,
    IconWidget,
    FluentIconBase,
    BodyLabel,
    CaptionLabel,
    isDarkTheme,
)


class QuickActionCard(CardWidget):
    """快速操作卡片，点击触发对应功能导航。"""

    clicked = Signal()

    def __init__(
        self,
        icon: FluentIconBase,
        title: str,
        desc: str = "",
        parent: Optional[QWidget] = None,
        *,
        compact: bool = False,
    ):
        super().__init__(parent)
        self._compact = compact
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(68 if compact else 84)

        layout = QVBoxLayout(self)
        if compact:
            layout.setContentsMargins(10, 7, 10, 7)
            layout.setSpacing(4 if not desc else 4)
        else:
            layout.setContentsMargins(10, 8, 10, 8)
            layout.setSpacing(8 if not desc else 6)
        layout.setAlignment(Qt.AlignCenter)

        self.icon_widget = IconWidget(icon, self)
        icon_px = 25 if compact else 28
        self.icon_widget.setFixedSize(icon_px, icon_px)
        layout.addWidget(self.icon_widget, 0, Qt.AlignCenter)

        self.title_label = BodyLabel(title, self)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setWordWrap(False)
        self.title_label.setToolTip(title)
        layout.addWidget(self.title_label, 0, Qt.AlignCenter)

        self.desc_label = None
        if desc:
            self.desc_label = CaptionLabel(desc, self)
            self.desc_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(self.desc_label, 0, Qt.AlignCenter)

        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(0)
        self._shadow.setOffset(0, 0)
        self._shadow.setColor(QColor(0, 0, 0, 0))
        self.setGraphicsEffect(self._shadow)

        self._apply_theme()

    def _apply_theme(self) -> None:
        dark = isDarkTheme()
        if self._compact:
            title_size = "12px"
        else:
            title_size = "14px" if self.desc_label else "15px"
        title_color = "#E0E0E0" if dark else "#1A1A1A"
        self.title_label.setStyleSheet(f"font-size: {title_size}; font-weight: 500; color: {title_color};")
        if self.desc_label:
            desc_color = "#AAAAAA" if dark else "#757575"
            self.desc_label.setStyleSheet(f"color: {desc_color};")

        bg = "rgba(255, 255, 255, 0.04)" if dark else "#FFFFFF"
        border = "rgba(255, 255, 255, 0.08)" if dark else "#EBEEF2"
        self.setStyleSheet(
            "CardWidget {"
            f"background: {bg};"
            f"border: 1px solid {border};"
            "border-radius: 8px;"
            "}"
            "CardWidget:hover {"
            f"border: 1px solid {'rgba(76, 194, 255, 0.38)' if dark else 'rgba(0, 120, 212, 0.28)'};"
            "}"
        )

    def enterEvent(self, event: QEnterEvent) -> None:
        super().enterEvent(event)
        dark = isDarkTheme()
        shadow_color = QColor(255, 255, 255, 18) if dark else QColor(0, 0, 0, 30)
        self._shadow.setColor(shadow_color)
        self._shadow.setBlurRadius(16)
        self._shadow.setOffset(0, 2)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self._shadow.setBlurRadius(0)
        self._shadow.setOffset(0, 0)
        self._shadow.setColor(QColor(0, 0, 0, 0))

    def mouseReleaseEvent(self, e) -> None:
        super().mouseReleaseEvent(e)
        self.clicked.emit()
