"""
浏览器页面（纯提示页）
文件路径：src/ui/pages/browser_page.py
功能：说明浏览器通过 Playwright 打开本地 Chrome，不集成 QWebEngineView。
"""

from typing import Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
import logging

from qfluentwidgets import SubtitleLabel, CaptionLabel

from .base_page import BasePage

logger = logging.getLogger(__name__)


class EmptyBrowserWidget(QWidget):
    """浏览器提示组件（无嵌入式浏览器）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        icon_label = QLabel("🌐", self)
        icon_label.setStyleSheet("font-size: 64px;")
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)
        title = SubtitleLabel("浏览器", self)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        hint = CaptionLabel(
            "在账号管理中双击账号，将使用本地 Chrome 打开；已打开的窗口可在任务栏查看。",
            self
        )
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint)


class BrowserPage(BasePage):
    """浏览器提示页（仅 Playwright，无 QWebEngineView 标签）"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("浏览器", parent)
        self._is_initialized = False
        self.account_manager = None
        self.empty_widget: Optional[EmptyBrowserWidget] = None

    def _ensure_initialized(self):
        if self._is_initialized:
            return
        self.empty_widget = EmptyBrowserWidget(self)
        self.content_layout.addWidget(self.empty_widget, stretch=1)
        self._is_initialized = True
        logger.debug("浏览器页面已初始化为纯提示页")

    def is_initialized(self) -> bool:
        return self._is_initialized

    def showEvent(self, event: QShowEvent):
        super().showEvent(event)
        if not self._is_initialized:
            self._ensure_initialized()

    def load_account_with_cookie(
        self,
        account_id: int,
        platform_username: str = "",
        platform: str = "",
        platform_url: str = "",
        profile_folder_name: str = None,
    ):
        """已废弃：浏览器仅通过 Playwright 打开，此处不再加载账号。保留为空实现以免调用方报错。"""
        logger.info("浏览器页为纯提示页，请使用账号管理双击打开 Patchright 浏览器")
