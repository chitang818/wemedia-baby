"""
快速操作卡片组件
文件路径：src/ui/components/quick_action_card.py
功能：显示主要操作的可点击卡片，包含大图标、标题和描述，支持悬浮效果与深色主题
"""

from typing import Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGraphicsDropShadowEffect
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QCursor, QColor, QEnterEvent

from qfluentwidgets import (
    CardWidget, IconWidget, FluentIconBase, BodyLabel, CaptionLabel, isDarkTheme
)


class QuickActionCard(CardWidget):
    """快速操作卡片，点击触发对应功能导航"""

    clicked = Signal()

    def __init__(
        self,
        icon: FluentIconBase,
        title: str,
        desc: str = "",
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setFixedHeight(84)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(8 if not desc else 6)

        self.icon_widget = IconWidget(icon, self)
        self.icon_widget.setFixedSize(28, 28)
        layout.addWidget(self.icon_widget, 0, Qt.AlignCenter)

        self.title_label = BodyLabel(title, self)
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

    def _apply_theme(self):
        dark = isDarkTheme()
        title_size = "14px" if self.desc_label else "15px"
        title_color = "#E0E0E0" if dark else "#1A1A1A"
        self.title_label.setStyleSheet(f"font-size: {title_size}; color: {title_color};")
        if self.desc_label:
            desc_color = "#AAAAAA" if dark else "#757575"
            self.desc_label.setStyleSheet(f"color: {desc_color};")

    def enterEvent(self, event: QEnterEvent):
        super().enterEvent(event)
        dark = isDarkTheme()
        shadow_color = QColor(255, 255, 255, 18) if dark else QColor(0, 0, 0, 30)
        self._shadow.setColor(shadow_color)
        self._shadow.setBlurRadius(16)
        self._shadow.setOffset(0, 2)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._shadow.setBlurRadius(0)
        self._shadow.setOffset(0, 0)
        self._shadow.setColor(QColor(0, 0, 0, 0))

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        self.clicked.emit()
