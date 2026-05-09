"""
骨架屏组件 — 使用 QPropertyAnimation 驱动平滑呼吸动画，
并支持骨架→真实内容的淡出过渡。
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGraphicsOpacityEffect,
)
from PySide6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QSequentialAnimationGroup,
    QTimer, Property,
)
from PySide6.QtGui import QPainter, QColor, QBrush


class SkeletonItem(QWidget):
    """单个骨架屏占位条，内置平滑的 opacity 呼吸动画。"""

    def __init__(self, parent=None, radius=4):
        super().__init__(parent)
        self.radius = radius
        self.setFixedHeight(20)

        self._alpha: float = 0.40
        self._min_alpha: float = 0.22
        self._max_alpha: float = 0.62

        self._breathing_group: QSequentialAnimationGroup | None = None

    # --- Qt Property：供 QPropertyAnimation 驱动 ---

    def _get_alpha(self) -> float:
        return self._alpha

    def _set_alpha(self, v: float):
        self._alpha = v
        self.update()

    alphaValue = Property(float, _get_alpha, _set_alpha)

    # --- 呼吸动画 ---

    def start_breathing(self):
        if self._breathing_group and self._breathing_group.state() == QSequentialAnimationGroup.Running:
            return

        group = QSequentialAnimationGroup(self)

        fade_out = QPropertyAnimation(self, b"alphaValue", self)
        fade_out.setDuration(900)
        fade_out.setStartValue(self._max_alpha)
        fade_out.setEndValue(self._min_alpha)
        fade_out.setEasingCurve(QEasingCurve.InOutSine)

        fade_in = QPropertyAnimation(self, b"alphaValue", self)
        fade_in.setDuration(900)
        fade_in.setStartValue(self._min_alpha)
        fade_in.setEndValue(self._max_alpha)
        fade_in.setEasingCurve(QEasingCurve.InOutSine)

        group.addAnimation(fade_out)
        group.addAnimation(fade_in)
        group.setLoopCount(-1)

        self._breathing_group = group
        group.start()

    def stop_breathing(self):
        if self._breathing_group:
            self._breathing_group.stop()

    # --- 绘制 ---

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        try:
            from qfluentwidgets import isDarkTheme
            is_dark = isDarkTheme()
        except ImportError:
            is_dark = False

        a = int(self._alpha * 255)
        color = QColor(80, 80, 80, a) if is_dark else QColor(200, 200, 200, a)
        painter.setBrush(QBrush(color))
        painter.drawRoundedRect(self.rect(), self.radius, self.radius)


class SkeletonTable(QWidget):
    """骨架屏表格（模拟列表加载状态），支持淡出过渡。"""

    _FADE_OUT_MS = 200

    def __init__(self, rows=5, columns=4, parent=None):
        super().__init__(parent)
        self.rows = rows
        self.columns = columns
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(16)
        header_layout.setContentsMargins(24, 0, 24, 0)
        for _ in range(self.columns):
            item = SkeletonItem(self)
            item.setFixedHeight(24)
            header_layout.addWidget(item)
        layout.addLayout(header_layout)

        layout.addSpacing(4)

        for r in range(self.rows):
            row_layout = QHBoxLayout()
            row_layout.setSpacing(16)
            row_layout.setContentsMargins(24, 0, 24, 0)

            avatar = SkeletonItem(self, radius=16)
            avatar.setFixedSize(32, 32)
            row_layout.addWidget(avatar)

            for _ in range(self.columns - 1):
                item = SkeletonItem(self)
                item.setFixedHeight(16)
                row_layout.addWidget(item)

            layout.addLayout(row_layout)

        layout.addStretch()

    # --- 生命周期 ---

    def showEvent(self, event):
        super().showEvent(event)
        for child in self.findChildren(SkeletonItem):
            child.start_breathing()

    def hideEvent(self, event):
        super().hideEvent(event)
        for child in self.findChildren(SkeletonItem):
            child.stop_breathing()

    # --- 淡出过渡 ---

    def fade_out(self, on_finished=None):
        """播放淡出动画；完成后调用 on_finished 回调（适合在回调中切换 StackedWidget）。"""
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(1.0)
        self.setGraphicsEffect(effect)

        ani = QPropertyAnimation(effect, b"opacity", self)
        ani.setDuration(self._FADE_OUT_MS)
        ani.setStartValue(1.0)
        ani.setEndValue(0.0)
        ani.setEasingCurve(QEasingCurve.InCubic)

        def _cleanup():
            self.setGraphicsEffect(None)
            if on_finished:
                on_finished()

        ani.finished.connect(_cleanup)
        self._fade_ani = ani
        ani.start()
