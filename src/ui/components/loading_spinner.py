"""
通用加载指示器组件

提供 LoadingSpinner（居中转圈 + 可选文案）和 LoadingOverlay（半透明遮罩层），
可在页面或卡片中灵活使用，替代纯文字「加载中…」。
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGraphicsOpacityEffect,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve

from qfluentwidgets import IndeterminateProgressRing, BodyLabel, isDarkTheme


class LoadingSpinner(QWidget):
    """居中显示的加载转圈 + 文案，可直接放进布局或作为 overlay 的子控件。"""

    def __init__(self, text: str = "", ring_size: int = 32, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(12)

        self._ring = IndeterminateProgressRing(self)
        self._ring.setFixedSize(ring_size, ring_size)
        layout.addWidget(self._ring, alignment=Qt.AlignCenter)

        self._label = BodyLabel(text, self)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setVisible(bool(text))
        layout.addWidget(self._label, alignment=Qt.AlignCenter)

    def set_text(self, text: str):
        self._label.setText(text)
        self._label.setVisible(bool(text))


class LoadingOverlay(QWidget):
    """半透明遮罩 + 居中 LoadingSpinner，覆盖在父控件上方。

    用法::

        self._overlay = LoadingOverlay("加载中…", parent=self)
        self._overlay.show_animated()
        # ... 数据就绪后 ...
        self._overlay.hide_animated()
    """

    _FADE_MS = 200

    def __init__(self, text: str = "", ring_size: int = 36, parent=None):
        super().__init__(parent)
        self.setObjectName("LoadingOverlay")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        self._spinner = LoadingSpinner(text, ring_size, self)
        layout.addWidget(self._spinner)

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._ani: QPropertyAnimation | None = None

    def set_text(self, text: str):
        self._spinner.set_text(text)

    # ------ show / hide ------

    def show_animated(self):
        self._sync_geometry()
        self.setVisible(True)
        self.raise_()
        self._animate_opacity(0.0, 1.0)

    def hide_animated(self):
        ani = self._animate_opacity(1.0, 0.0)
        if ani:
            ani.finished.connect(lambda: self.setVisible(False))
        else:
            self.setVisible(False)

    def show_immediate(self):
        self._sync_geometry()
        self._opacity_effect.setOpacity(1.0)
        self.setVisible(True)
        self.raise_()

    def hide_immediate(self):
        self._opacity_effect.setOpacity(0.0)
        self.setVisible(False)

    # ------ 内部 ------

    def _animate_opacity(self, start: float, end: float):
        if self._ani is not None:
            self._ani.stop()
        ani = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        ani.setDuration(self._FADE_MS)
        ani.setStartValue(start)
        ani.setEndValue(end)
        ani.setEasingCurve(QEasingCurve.InOutCubic)
        self._ani = ani
        ani.start()
        return ani

    def _sync_geometry(self):
        p = self.parentWidget()
        if p:
            self.setGeometry(0, 0, p.width(), p.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QColor
        painter = QPainter(self)
        bg = QColor(32, 32, 32, 120) if isDarkTheme() else QColor(255, 255, 255, 160)
        painter.fillRect(self.rect(), bg)
        painter.end()
        super().paintEvent(event)
