"""单条发布页等场景用的视频预览：在 QFluentWidgets VideoWidget 基础上为播放条预留底部区域，避免控制条遮挡画面。"""

from PySide6.QtCore import QSizeF, Qt
from PySide6.QtWidgets import QGraphicsView

from qfluentwidgets.multimedia import VideoWidget as QfwVideoWidget

# 与 qfluentwidgets.multimedia.video_widget.VideoWidget.resizeEvent 中 playBar 边距一致
_PLAY_BAR_MARGIN = 11


class PreviewVideoWidget(QfwVideoWidget):
    """将 QGraphicsVideoItem 限制在「视口高度 − 播放条」区域内，并顶对齐；播放条叠在底部留白上而非画面上。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

    def resizeEvent(self, event):
        # 勿调用 QfwVideoWidget.resizeEvent：其实现用整窗 fitInView，会把画面铺到播放条下方造成遮挡。
        QGraphicsView.resizeEvent(self, event)
        bar_h = self.playBar.height()
        w = max(1, self.width())
        h = max(1, self.height())
        m = _PLAY_BAR_MARGIN
        video_h = max(1, h - bar_h - 2 * m)
        self.videoItem.setSize(QSizeF(w, video_h))
        self.fitInView(self.videoItem, Qt.AspectRatioMode.KeepAspectRatio)
        self.playBar.move(m, h - bar_h - m)
        self.playBar.setFixedSize(w - 2 * m, bar_h)
