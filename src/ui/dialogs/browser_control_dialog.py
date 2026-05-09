# -*- coding: utf-8 -*-
"""
浏览器控制对话框
文件路径：src/ui/dialogs/browser_control_dialog.py
功能：显示浏览器操作状态，提供手动操作按钮，解耦后端逻辑
"""

import logging
from typing import Optional, Callable
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QWidget

from src.ui.components.base_dialog import install_escape_reject_shortcut, resolve_top_level_window_parent

try:
    from qfluentwidgets import InfoBar, PrimaryPushButton, PushButton, BodyLabel
    FLUENT_WIDGETS_AVAILABLE = True
except ImportError:
    FLUENT_WIDGETS_AVAILABLE = False

logger = logging.getLogger(__name__)

class BrowserControlDialog(QDialog):
    """浏览器控制/状态对话框"""
    
    # 定义信号供外部连接
    manual_save_clicked = Signal()
    manual_update_clicked = Signal()
    close_browser_clicked = Signal()
    
    def __init__(self, parent: QWidget, account_name: str, platform: str, is_new_account: bool = False):
        super().__init__(resolve_top_level_window_parent(parent))
        install_escape_reject_shortcut(self)
        self.account_name = account_name
        self.platform = platform
        self.is_new_account = is_new_account
        self._init_ui()
        
    def _init_ui(self):
        title = "添加新账号" if self.is_new_account else f"正在控制: {self.account_name}"
        self.setWindowTitle(title)
        self.setFixedWidth(400)
        
        layout = QVBoxLayout(self)
        
        # 1. 信息提示
        if self.is_new_account:
            msg = "⚡ 浏览器已打开\n\n请在浏览器中完成登录操作。\n软件将自动检测登录状态并保存账号。"
        else:
            msg = f"浏览器已打开 ({self.platform})，请进行操作。\n软件将自动同步最新Cookie和昵称。"
            
        self.info_label = QLabel(msg)
        self.info_label.setWordWrap(True)
        # 增加字体大小
        font = self.info_label.font()
        font.setPointSize(11)
        self.info_label.setFont(font)
        layout.addWidget(self.info_label)
        
        # 2. 状态标签
        self.status_label = QLabel("正在初始化...", self)
        self.status_label.setObjectName("status_label")
        self.status_label.setStyleSheet("color: #666666; font-style: italic;")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # 3. 操作按钮区域
        if not self.is_new_account:
            # 存量账号：手动更新
            btn_text = "手动更新信息"
            if FLUENT_WIDGETS_AVAILABLE:
                self.btn_action = PrimaryPushButton(btn_text, self)
            else:
                self.btn_action = QPushButton(btn_text, self)
            self.btn_action.clicked.connect(self.manual_update_clicked.emit)
            layout.addWidget(self.btn_action)
        else:
            # 新账号：手动保存
            if FLUENT_WIDGETS_AVAILABLE:
                self.btn_manual = PushButton("手动保存 (如果自动检测失败)", self)
            else:
                self.btn_manual = QPushButton("手动保存 (如果自动检测失败)", self)
            self.btn_manual.clicked.connect(self.manual_save_clicked.emit)
            layout.addWidget(self.btn_manual)
            
            # 更新初始状态文本
            self.update_status("正在等待登录...")
        
        # 4. 关闭按钮
        if FLUENT_WIDGETS_AVAILABLE:
            self.btn_close = PushButton("关闭浏览器", self)
        else:
            self.btn_close = QPushButton("关闭浏览器", self)
        self.btn_close.clicked.connect(self.close_browser_clicked.emit)
        layout.addWidget(self.btn_close)
        
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def update_status(self, text: str):
        """更新状态文本"""
        self.status_label.setText(text)

    def close_programmatically(self):
        """程序化关闭弹窗（账号保存成功后由主流程调用），不触发 close_browser_clicked 信号。"""
        self._suppress_close_signal = True
        self.close()

    def closeEvent(self, event):
        """窗口关闭时触发；程序化关闭（close_programmatically）时跳过信号，避免重复触发浏览器关闭。"""
        if not getattr(self, "_suppress_close_signal", False):
            self.close_browser_clicked.emit()
        super().closeEvent(event)
