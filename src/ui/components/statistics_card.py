"""
统计卡片组件
文件路径：src/ui/components/statistics_card.py
功能：显示单一统计指标的卡片，包含图标、标题、数值和描述；支持骨架屏加载与数值淡入。
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Optional

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSizePolicy,
)
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt, QTimer, QVariantAnimation, QEasingCurve

from qfluentwidgets import (
    CardWidget,
    CaptionLabel,
    TitleLabel,
    BodyLabel,
    IconWidget,
    FluentIconBase,
    FluentIcon,
    isDarkTheme,
)

from src.ui.components.skeleton import SkeletonItem
from src.ui.workspace_chart_animation_prefs import STATS_SKELETON_MIN_MS, STATS_VALUE_FADE_MS

BORDER_COLORS = {
    FluentIcon.PEOPLE: "#0078D4",
    FluentIcon.SEND: "#107C10",
    FluentIcon.FOLDER: "#FFB900",
    FluentIcon.ACCEPT: "#5C2D91",
    FluentIcon.MOVIE: "#0078D4",
    FluentIcon.PHOTO: "#D83B01" if hasattr(FluentIcon, "PHOTO") else "#D83B01",
}


class StatCardLoadState(Enum):
    LOADING = "loading"
    READY = "ready"


class StatisticsCard(CardWidget):
    """统计卡片组件，自动适配深色/浅色主题。"""

    def __init__(
        self,
        title: str,
        value: str,
        desc: str,
        icon: Optional[FluentIconBase] = None,
        parent: Optional[QWidget] = None,
        *,
        compact: bool = False,
    ):
        super().__init__(parent)
        self.icon_enum = icon
        self._compact = compact
        self._value_color = "#0078D4"
        self._value_font_px_default = 26 if compact else 28
        self._value_font_px_percent = 22 if compact else 24
        self._load_state = StatCardLoadState.READY
        self._loading_shown_at = 0.0
        self._reveal_timer: Optional[QTimer] = None
        self._value_skeleton: Optional[SkeletonItem] = None
        self._value_fade_ani: Optional[QVariantAnimation] = None

        self.setMinimumHeight(78 if compact else 90)
        self.setMinimumWidth(160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self._init_ui(title, value, desc)
        self._apply_theme()

    @property
    def is_value_loading(self) -> bool:
        return self._load_state == StatCardLoadState.LOADING

    def _init_ui(self, title: str, value: str, desc: str):
        layout = QHBoxLayout(self)
        if self._compact:
            layout.setContentsMargins(14, 8, 16, 8)
            layout.setSpacing(10)
        else:
            layout.setContentsMargins(16, 10, 18, 10)
            layout.setSpacing(12)

        if self.icon_enum:
            self.icon_widget = IconWidget(self.icon_enum, self)
            icon_size = 20 if self._compact else 22
            self.icon_widget.setFixedSize(icon_size, icon_size)
            layout.addWidget(self.icon_widget, 0, Qt.AlignVCenter)

        text_container = QWidget()
        text_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        text_layout.setAlignment(Qt.AlignVCenter)

        self.title_label = BodyLabel(title, self)
        self.desc_label = CaptionLabel(desc, self)
        try:
            self.title_label.setWordWrap(False)
            self.desc_label.setWordWrap(False)
            self.desc_label.setToolTip(desc)
        except Exception:
            pass

        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.desc_label)
        layout.addWidget(text_container, 1)

        self._value_host = QWidget(self)
        self._value_host.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        value_host_layout = QVBoxLayout(self._value_host)
        value_host_layout.setContentsMargins(0, 0, 0, 0)
        value_host_layout.setSpacing(0)

        self.value_label = TitleLabel(value, self._value_host)
        self.value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.value_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        value_host_layout.addWidget(self.value_label)

        layout.addWidget(self._value_host, 0, Qt.AlignVCenter)

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
        try:
            title_h = int(self.title_label.fontMetrics().height()) + 2
            desc_h = int(self.desc_label.fontMetrics().height()) + 2
            self.title_label.setFixedHeight(max(18, title_h))
            self.desc_label.setFixedHeight(max(14, desc_h))
        except Exception:
            return

    def _apply_value_style(self, color: Optional[str] = None) -> None:
        try:
            txt = str(self.value_label.text() or "")
        except Exception:
            txt = ""
        font_px = self._value_font_px_percent if ("%" in txt and len(txt) >= 4) else self._value_font_px_default
        value_color = color or self._value_color
        self.value_label.setStyleSheet(
            f"font-size: {font_px}px; font-weight: bold; color: {value_color}; "
            f"font-family: 'Segoe UI', 'Microsoft YaHei UI';"
        )
        self._sync_value_width()

    def _sync_value_width(self) -> None:
        try:
            text_width = self.value_label.fontMetrics().horizontalAdvance(str(self.value_label.text() or "0"))
            min_width = max(44, text_width + 8)
            self.value_label.setMinimumWidth(min_width)
            self._value_host.setMinimumWidth(min_width)
            self.value_label.updateGeometry()
            self._value_host.updateGeometry()
        except Exception:
            pass

    def show_value_loading(self) -> None:
        """数值区进入加载态：骨架条 + 占位符。"""
        self.cancel_pending_reveal()
        self._load_state = StatCardLoadState.LOADING
        self._loading_shown_at = time.monotonic()
        self.value_label.setText("—")
        self._apply_value_style()
        self.value_label.hide()
        self._show_value_skeleton()

    def reveal(self, value: str, desc: str, *, animate: bool = False) -> None:
        """数据就绪后展示数值与描述；首次加载可带最短骨架时长与淡入。"""
        self.cancel_pending_reveal()
        value_s, desc_s = str(value), str(desc)

        if self._load_state == StatCardLoadState.LOADING and animate:
            elapsed_ms = (time.monotonic() - self._loading_shown_at) * 1000.0
            delay = max(0, int(STATS_SKELETON_MIN_MS - elapsed_ms))

            def _commit() -> None:
                self._finish_reveal(value_s, desc_s, fade_in=True)

            self._reveal_timer = QTimer(self)
            self._reveal_timer.setSingleShot(True)
            self._reveal_timer.timeout.connect(_commit)
            self._reveal_timer.start(delay)
            return

        self._finish_reveal(value_s, desc_s, fade_in=animate)

    def cancel_pending_reveal(self) -> None:
        if self._reveal_timer is None:
            return
        try:
            self._reveal_timer.stop()
            self._reveal_timer.deleteLater()
        except Exception:
            pass
        self._reveal_timer = None

    def _finish_reveal(self, value: str, desc: str, *, fade_in: bool) -> None:
        self._reveal_timer = None
        self._hide_value_skeleton()
        self._load_state = StatCardLoadState.READY
        self.value_label.show()
        self.set_value(value)
        self.set_description(desc)
        if fade_in:
            self._fade_in_value_label()

    def _fade_in_value_label(self) -> None:
        if self._value_fade_ani is not None:
            try:
                self._value_fade_ani.stop()
            except Exception:
                pass

        # Avoid a child QGraphicsOpacityEffect here. Workspace pages can already
        # be animated by a parent effect, and nested effects may disappear after
        # a maximized-window repaint on Windows/PySide.
        self.value_label.show()
        self.value_label.raise_()
        base = QColor(self._value_color)
        if not base.isValid():
            base = QColor("#0078D4")

        ani = QVariantAnimation(self)
        ani.setDuration(STATS_VALUE_FADE_MS)
        ani.setStartValue(0)
        ani.setEndValue(255)
        ani.setEasingCurve(QEasingCurve.OutCubic)

        def _apply_alpha(alpha: int) -> None:
            self._apply_value_style(f"rgba({base.red()}, {base.green()}, {base.blue()}, {alpha})")

        ani.valueChanged.connect(lambda value: _apply_alpha(int(value)))
        ani.finished.connect(lambda: self._apply_value_style(self._value_color))
        self._value_fade_ani = ani
        ani.start()

    def _show_value_skeleton(self) -> None:
        self._hide_value_skeleton()
        sk = SkeletonItem(self._value_host, radius=6)
        sk.setFixedSize(52 if self._compact else 56, 24 if self._compact else 28)
        sk.start_breathing()
        self._value_skeleton = sk
        host_layout = self._value_host.layout()
        if host_layout is not None:
            host_layout.addWidget(sk, 0, Qt.AlignRight | Qt.AlignVCenter)

    def _hide_value_skeleton(self) -> None:
        if self._value_skeleton is None:
            return
        try:
            self._value_skeleton.stop_breathing()
        except Exception:
            pass
        try:
            host_layout = self._value_host.layout()
            if host_layout is not None:
                host_layout.removeWidget(self._value_skeleton)
        except Exception:
            pass
        self._value_skeleton.deleteLater()
        self._value_skeleton = None

    def set_value(self, value: str):
        self.value_label.setText(str(value))
        self._apply_value_style()
        if self._load_state == StatCardLoadState.READY:
            self.value_label.show()

    def set_description(self, desc: str):
        self.desc_label.setText(desc)
        try:
            self.desc_label.setToolTip(desc)
        except Exception:
            pass

    def hideEvent(self, event) -> None:
        self.cancel_pending_reveal()
        super().hideEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._load_state == StatCardLoadState.READY:
            self.value_label.show()
            self._sync_value_width()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._load_state == StatCardLoadState.READY:
            self._sync_value_width()
