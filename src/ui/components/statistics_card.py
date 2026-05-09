"""
统计卡片组件
文件路径：src/ui/components/statistics_card.py
功能：显示单一统计指标的卡片，包含图标、标题、数值和描述
"""

from typing import Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt

from qfluentwidgets import (
    CardWidget, CaptionLabel, TitleLabel, BodyLabel,
    IconWidget, FluentIconBase, FluentIcon, isDarkTheme
)

BORDER_COLORS = {
    FluentIcon.PEOPLE: "#0078D4",
    FluentIcon.SEND: "#107C10",
    FluentIcon.FOLDER: "#FFB900",
    FluentIcon.ACCEPT: "#5C2D91",
    # 媒体库相关
    FluentIcon.MOVIE: "#0078D4",
    FluentIcon.PHOTO: "#D83B01" if hasattr(FluentIcon, "PHOTO") else "#D83B01",
}


class StatisticsCard(CardWidget):
    """统计卡片组件，自动适配深色/浅色主题"""

    def __init__(
        self,
        title: str,
        value: str,
        desc: str,
        icon: Optional[FluentIconBase] = None,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.icon_enum = icon
        self._value_color = "#0078D4"
        self._value_font_px_default = 28
        self._value_font_px_percent = 24

        # 以前固定高度 80，在 125%/150% DPI 或描述变长时容易“被裁切/遮挡”
        # 改为最小高度 + Preferred，让布局在需要时自动撑开
        # 顶部四卡偏“仪表盘”风格：更扁平紧凑，避免还原窗口显得臃肿
        # 还原窗口 + 高 DPI 下，字体行高会变大；最小高度略回调以避免裁切
        self.setMinimumHeight(90)
        self.setMinimumWidth(160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self._init_ui(title, value, desc)
        self._apply_theme()

    def _init_ui(self, title: str, value: str, desc: str):
        layout = QHBoxLayout(self)
        # 顶部四卡在还原窗口下更紧凑
        layout.setContentsMargins(16, 10, 18, 10)
        layout.setSpacing(12)

        if self.icon_enum:
            self.icon_widget = IconWidget(self.icon_enum, self)
            self.icon_widget.setFixedSize(22, 22)
            layout.addWidget(self.icon_widget, 0, Qt.AlignVCenter)

        text_container = QWidget()
        text_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        # 内容垂直居中，视觉更“卡片化”；高度不足的问题由最小高度与内边距兜底
        text_layout.setAlignment(Qt.AlignVCenter)

        self.title_label = BodyLabel(title, self)
        self.desc_label = CaptionLabel(desc, self)
        # 顶部统计卡片以“单行信息”为主，避免还原窗口时因为换行导致高度不够而裁切
        # 文案太长时允许被截断，完整内容可通过 tooltip 查看
        try:
            self.title_label.setWordWrap(False)
        except Exception:
            pass
        try:
            self.desc_label.setWordWrap(False)
        except Exception:
            pass
        try:
            self.desc_label.setToolTip(desc)
        except Exception:
            pass

        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.desc_label)
        layout.addWidget(text_container)

        layout.addStretch(1)

        self.value_label = TitleLabel(value, self)
        self.value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.value_label, 0, Qt.AlignVCenter)

    def _apply_theme(self):
        dark = isDarkTheme()

        title_color = "#E0E0E0" if dark else "#333333"
        desc_color = "#AAAAAA" if dark else "#757575"
        self.title_label.setStyleSheet(f"color: {title_color}; font-weight: 600; font-size: 14px;")
        self.desc_label.setStyleSheet(f"color: {desc_color}; font-size: 12px;")

        value_color = "#4CC2FF" if dark else "#0078D4"
        try:
            from ..styles.theme_manager import theme_manager
            tc = theme_manager.get_theme_color()
            if dark:
                c = QColor(tc)
                value_color = c.lighter(140).name()
            else:
                value_color = tc
        except ImportError:
            pass
        self._value_color = value_color

        self._apply_value_style()
        self._apply_single_line_label_heights()

        border_color = BORDER_COLORS.get(self.icon_enum, "#0078D4")
        self.setStyleSheet(f"CardWidget {{ border-left: 4px solid {border_color}; }}")

    def _apply_single_line_label_heights(self) -> None:
        """按真实字体行高设置单行高度，避免在高 DPI 下被 setMaximumHeight 裁切。"""
        try:
            title_h = int(self.title_label.fontMetrics().height()) + 2
            desc_h = int(self.desc_label.fontMetrics().height()) + 2
            # 只限制“最多一行”，但高度按行高走，避免字底被裁掉
            self.title_label.setFixedHeight(max(18, title_h))
            self.desc_label.setFixedHeight(max(14, desc_h))
        except Exception:
            return

    def _apply_value_style(self) -> None:
        """根据内容类型（如百分比）动态调整字号，避免还原窗口遮挡。"""
        try:
            txt = str(self.value_label.text() or "")
        except Exception:
            txt = ""
        font_px = self._value_font_px_percent if ("%" in txt and len(txt) >= 4) else self._value_font_px_default
        self.value_label.setStyleSheet(
            f"font-size: {font_px}px; font-weight: bold; color: {self._value_color}; "
            f"font-family: 'Segoe UI', 'Microsoft YaHei UI';"
        )

    def set_value(self, value: str):
        self.value_label.setText(str(value))
        self._apply_value_style()

    def set_description(self, desc: str):
        self.desc_label.setText(desc)
        try:
            self.desc_label.setToolTip(desc)
        except Exception:
            pass
