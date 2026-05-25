"""
媒体库合并统计卡（视频库 + 图片库单行展示）
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Optional

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy, QFrame
from PySide6.QtCore import Qt, QTimer

from qfluentwidgets import (
    CardWidget,
    CaptionLabel,
    BodyLabel,
    TitleLabel,
    IconWidget,
    FluentIcon,
    isDarkTheme,
)

from src.ui.components.skeleton import SkeletonItem
from src.ui.utils.fluent_tooltips import ToolTipPosition, install_fluent_tool_tip
from src.ui.workspace_chart_animation_prefs import STATS_SKELETON_MIN_MS


class MediaCombinedLoadState(Enum):
    LOADING = "loading"
    READY = "ready"


class MediaLibraryCombinedCard(CardWidget):
    """工作台顶部：视频与图片库占用情况合并为一张卡。"""

    _VALUE_FONT_PX = 24

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._load_state = MediaCombinedLoadState.READY
        self._loading_shown_at = 0.0
        self._reveal_timer: Optional[QTimer] = None
        self._skeleton: Optional[SkeletonItem] = None
        self._value_color = "#0078D4"

        self.setMinimumHeight(78)
        self.setMinimumWidth(160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self._main_layout = QHBoxLayout(self)
        self._main_layout.setContentsMargins(14, 8, 18, 10)
        self._main_layout.setSpacing(9)

        self._movie_icon = IconWidget(FluentIcon.MOVIE, self)
        self._movie_icon.setFixedSize(20, 20)
        self._main_layout.addWidget(self._movie_icon, 0, Qt.AlignmentFlag.AlignVCenter)

        self._text_host = QWidget(self)
        self._text_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        text_layout = QVBoxLayout(self._text_host)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(0)
        text_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._title_label = BodyLabel("素材库", self._text_host)
        try:
            self._title_label.setWordWrap(False)
        except Exception:
            pass
        text_layout.addWidget(self._title_label)
        self._main_layout.addWidget(self._text_host, 1)

        self._metrics_host = self._build_metrics_host()
        self._main_layout.addWidget(self._metrics_host, 0, Qt.AlignmentFlag.AlignVCenter)

        self._apply_theme()
        self._apply_title_height()
        self._install_metric_fluent_tooltips()

    @staticmethod
    def _bind_fluent_tooltip(
        widget: QWidget,
        text: str,
        *,
        position: ToolTipPosition = ToolTipPosition.TOP,
    ) -> None:
        """Fluent 自绘悬停提示，避免 Windows 原生 QToolTip 黑底深字。"""
        tip = (text or "").strip()
        widget.setToolTip(tip)
        if tip:
            install_fluent_tool_tip(widget, position=position)

    def _install_metric_fluent_tooltips(self) -> None:
        for widget in (self._video_value, self._image_value):
            install_fluent_tool_tip(widget, position=ToolTipPosition.TOP)

    def _build_metrics_host(self) -> QWidget:
        host = QWidget(self)
        host.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        metrics_layout = QHBoxLayout(host)
        metrics_layout.setContentsMargins(0, 0, 0, 0)
        metrics_layout.setSpacing(10)
        metrics_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._video_block = self._make_metric_block("视频", host)
        metrics_layout.addWidget(self._video_block, 0, Qt.AlignmentFlag.AlignVCenter)

        self._separator = QFrame(host)
        self._separator.setFrameShape(QFrame.Shape.VLine)
        self._separator.setFrameShadow(QFrame.Shadow.Sunken)
        self._separator.setFixedWidth(1)
        metrics_layout.addWidget(self._separator, 0, Qt.AlignmentFlag.AlignVCenter)

        self._image_block = self._make_metric_block("图片", host)
        metrics_layout.addWidget(self._image_block, 0, Qt.AlignmentFlag.AlignVCenter)

        return host

    def _make_metric_block(self, kind: str, parent: QWidget) -> QWidget:
        block = QWidget(parent)
        bl = QVBoxLayout(block)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(2)
        bl.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)

        cap = CaptionLabel(kind, block)
        cap.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        val = TitleLabel("—", block)
        val.setObjectName(f"mediaCombined{kind}Value")
        val.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        bl.addWidget(cap)
        bl.addWidget(val)
        if kind == "视频":
            self._video_value = val
        else:
            self._image_value = val
        return block

    def _resolve_value_color(self) -> str:
        dark = isDarkTheme()
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
        return value_color

    def _apply_value_style(self) -> None:
        value_color = self._value_color
        style = (
            f"font-size: {self._VALUE_FONT_PX}px; font-weight: bold; color: {value_color}; "
            "font-family: 'Segoe UI', 'Microsoft YaHei UI';"
        )
        for val in (self._video_value, self._image_value):
            val.setStyleSheet(style)
        self._sync_metric_widths()

    def _sync_metric_widths(self) -> None:
        try:
            for val in (self._video_value, self._image_value):
                text_width = val.fontMetrics().horizontalAdvance(str(val.text() or "0"))
                min_width = max(36, text_width + 4)
                val.setMinimumWidth(min_width)
        except Exception:
            pass

    def _apply_title_height(self) -> None:
        try:
            title_h = int(self._title_label.fontMetrics().height()) + 2
            self._title_label.setFixedHeight(max(18, title_h))
        except Exception:
            return

    def _apply_theme(self) -> None:
        dark = isDarkTheme()
        self._value_color = self._resolve_value_color()

        title_color = "#E0E0E0" if dark else "#333333"
        self._title_label.setStyleSheet(f"color: {title_color}; font-weight: 600; font-size: 13px;")
        self._apply_value_style()

        sep_color = "rgba(255, 255, 255, 0.15)" if dark else "#E0E0E0"
        self._separator.setStyleSheet(f"background: {sep_color}; border: none; max-width: 1px;")

        card_bg = "rgba(255, 255, 255, 0.045)" if dark else "#FFFFFF"
        border = "rgba(255, 255, 255, 0.08)" if dark else "#EBEEF2"
        self.setStyleSheet(
            "CardWidget {"
            f"background: {card_bg};"
            f"border: 1px solid {border};"
            "border-left: 4px solid #D83B01;"
            "border-radius: 8px;"
            "}"
        )

    @property
    def is_value_loading(self) -> bool:
        return self._load_state == MediaCombinedLoadState.LOADING

    def show_value_loading(self) -> None:
        self.cancel_pending_reveal()
        self._load_state = MediaCombinedLoadState.LOADING
        self._loading_shown_at = time.monotonic()
        self._video_value.setText("—")
        self._image_value.setText("—")
        self._apply_value_style()
        self._show_skeleton()

    def reveal(
        self,
        video_total: int,
        video_used: int,
        video_unused: int,
        image_total: int,
        image_used: int,
        image_unused: int,
        *,
        animate: bool = False,
    ) -> None:
        self.cancel_pending_reveal()
        if self._load_state == MediaCombinedLoadState.LOADING and animate:
            elapsed_ms = (time.monotonic() - self._loading_shown_at) * 1000.0
            delay = max(0, int(STATS_SKELETON_MIN_MS - elapsed_ms))

            def _commit() -> None:
                self._finish_reveal(
                    video_total,
                    video_used,
                    video_unused,
                    image_total,
                    image_used,
                    image_unused,
                )

            self._reveal_timer = QTimer(self)
            self._reveal_timer.setSingleShot(True)
            self._reveal_timer.timeout.connect(_commit)
            self._reveal_timer.start(delay)
            return
        self._finish_reveal(
            video_total,
            video_used,
            video_unused,
            image_total,
            image_used,
            image_unused,
        )

    def cancel_pending_reveal(self) -> None:
        if self._reveal_timer is None:
            return
        try:
            self._reveal_timer.stop()
            self._reveal_timer.deleteLater()
        except Exception:
            pass
        self._reveal_timer = None

    def _finish_reveal(
        self,
        video_total: int,
        video_used: int,
        video_unused: int,
        image_total: int,
        image_used: int,
        image_unused: int,
    ) -> None:
        self._reveal_timer = None
        self._hide_skeleton()
        self._load_state = MediaCombinedLoadState.READY

        self._video_value.setText(str(video_total))
        self._bind_fluent_tooltip(
            self._video_value,
            f"视频素材共 {video_total}，已占用 {video_used}，未占用 {video_unused}",
        )
        self._image_value.setText(str(image_total))
        self._bind_fluent_tooltip(
            self._image_value,
            f"图片素材共 {image_total}，已占用 {image_used}，未占用 {image_unused}",
        )
        self._apply_value_style()

    def _set_metrics_visible(self, visible: bool) -> None:
        for widget in (self._video_block, self._separator, self._image_block):
            if visible:
                widget.show()
            else:
                widget.hide()

    def _show_skeleton(self) -> None:
        self._hide_skeleton()
        self._set_metrics_visible(False)
        sk = SkeletonItem(self._metrics_host, radius=6)
        sk.setFixedSize(56, 24)
        sk.start_breathing()
        self._skeleton = sk
        host_layout = self._metrics_host.layout()
        if host_layout is not None:
            host_layout.addWidget(sk, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def _hide_skeleton(self) -> None:
        if self._skeleton is not None:
            try:
                self._skeleton.stop_breathing()
            except Exception:
                pass
            try:
                host_layout = self._metrics_host.layout()
                if host_layout is not None:
                    host_layout.removeWidget(self._skeleton)
            except Exception:
                pass
            self._skeleton.deleteLater()
            self._skeleton = None
        if self._load_state == MediaCombinedLoadState.READY:
            self._set_metrics_visible(True)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._load_state == MediaCombinedLoadState.READY:
            self._sync_metric_widths()
