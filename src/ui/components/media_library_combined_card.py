"""
媒体库合并统计卡（视频库 + 图片库单行展示）
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Optional

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy
from PySide6.QtCore import Qt, QTimer

from qfluentwidgets import (
    CardWidget,
    CaptionLabel,
    BodyLabel,
    IconWidget,
    FluentIcon,
    isDarkTheme,
)

from src.ui.components.skeleton import SkeletonItem
from src.ui.workspace_chart_animation_prefs import STATS_SKELETON_MIN_MS


class MediaCombinedLoadState(Enum):
    LOADING = "loading"
    READY = "ready"


class MediaLibraryCombinedCard(CardWidget):
    """工作台顶部：视频与图片库占用情况合并为一张卡。"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._load_state = MediaCombinedLoadState.READY
        self._loading_shown_at = 0.0
        self._reveal_timer: Optional[QTimer] = None
        self._skeleton: Optional[SkeletonItem] = None

        self.setMinimumHeight(78)
        self.setMinimumWidth(160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 16, 8)
        layout.setSpacing(10)

        _img_icon = getattr(FluentIcon, "PHOTO", getattr(FluentIcon, "PICTURE", FluentIcon.DOCUMENT))
        self._movie_icon = IconWidget(FluentIcon.MOVIE, self)
        self._movie_icon.setFixedSize(20, 20)
        layout.addWidget(self._movie_icon, 0, Qt.AlignVCenter)

        text_host = QWidget(self)
        text_layout = QVBoxLayout(text_host)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        self._title_label = BodyLabel("素材库", self)
        self._title_label.setStyleSheet("font-weight: 600; font-size: 14px;")
        text_layout.addWidget(self._title_label)
        layout.addWidget(text_host, 0, Qt.AlignVCenter)

        layout.addStretch(1)

        self._video_block = self._make_metric_block("视频", self)
        layout.addWidget(self._video_block, 0, Qt.AlignVCenter)

        sep = CaptionLabel("|", self)
        sep.setStyleSheet(f"color: {'#666' if isDarkTheme() else '#CCC'}; padding: 0 4px;")
        layout.addWidget(sep, 0, Qt.AlignVCenter)

        self._image_block = self._make_metric_block("图片", self)
        layout.addWidget(self._image_block, 0, Qt.AlignVCenter)

        self.setStyleSheet("CardWidget { border-left: 4px solid #D83B01; }")
        self._apply_theme()

    def _make_metric_block(self, kind: str, parent: QWidget) -> QWidget:
        block = QWidget(parent)
        bl = QVBoxLayout(block)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(2)
        bl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        cap = CaptionLabel(kind, block)
        cap.setAlignment(Qt.AlignRight)
        val = BodyLabel("—", block)
        val.setObjectName(f"mediaCombined{kind}Value")
        val.setAlignment(Qt.AlignRight)
        val.setStyleSheet("font-size: 20px; font-weight: bold;")
        bl.addWidget(cap)
        bl.addWidget(val)
        if kind == "视频":
            self._video_value = val
        else:
            self._image_value = val
        return block

    def _apply_theme(self) -> None:
        dark = isDarkTheme()
        color = "#4CC2FF" if dark else "#0078D4"
        title_color = "#E0E0E0" if dark else "#333333"
        self._title_label.setStyleSheet(f"color: {title_color}; font-weight: 600; font-size: 14px;")
        for val in (self._video_value, self._image_value):
            val.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {color};")

    @property
    def is_value_loading(self) -> bool:
        return self._load_state == MediaCombinedLoadState.LOADING

    def show_value_loading(self) -> None:
        self.cancel_pending_reveal()
        self._load_state = MediaCombinedLoadState.LOADING
        self._loading_shown_at = time.monotonic()
        self._video_value.setText("—")
        self._image_value.setText("—")
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
        self._video_value.setToolTip(
            f"视频素材共 {video_total}，已占用 {video_used}，未占用 {video_unused}"
        )
        self._image_value.setText(str(image_total))
        self._image_value.setToolTip(
            f"图片素材共 {image_total}，已占用 {image_used}，未占用 {image_unused}"
        )

    def _show_skeleton(self) -> None:
        self._hide_skeleton()
        sk = SkeletonItem(self, radius=6)
        sk.setFixedSize(80, 24)
        sk.start_breathing()
        self._skeleton = sk
        self.layout().addWidget(sk)

    def _hide_skeleton(self) -> None:
        if self._skeleton is None:
            return
        try:
            self.layout().removeWidget(self._skeleton)
        except Exception:
            pass
        self._skeleton.deleteLater()
        self._skeleton = None
