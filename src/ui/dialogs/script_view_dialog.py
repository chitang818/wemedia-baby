"""
脚本查看对话框
文件路径：src/ui/dialogs/script_view_dialog.py
功能：显示脚本文件内容
"""

from typing import Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout, QDialog, QTextEdit
from PySide6.QtCore import Qt
import logging

from src.ui.components.base_dialog import install_escape_reject_shortcut, resolve_top_level_window_parent

try:
    from qfluentwidgets import TextEdit, SubtitleLabel, PushButton

    FLUENT_WIDGETS_AVAILABLE = True
except ImportError:
    FLUENT_WIDGETS_AVAILABLE = False
    TextEdit = QTextEdit

logger = logging.getLogger(__name__)


class ScriptViewDialog(QDialog):
    """脚本查看对话框 - 显示脚本文件内容（QDialog + Fluent 子控件，避免误继承固定布局的 Dialog）。"""
    
    def __init__(self, script_content: str, file_name: str = "", parent: Optional[QWidget] = None):
        """初始化对话框
        
        Args:
            script_content: 脚本文件内容
            file_name: 文件名（用于显示标题）
            parent: 父窗口
        """
        super().__init__(resolve_top_level_window_parent(parent))
        install_escape_reject_shortcut(self)
        self.script_content = script_content
        self.file_name = file_name
        
        self._setup_ui()
    
    def _setup_ui(self):
        """设置UI"""
        if FLUENT_WIDGETS_AVAILABLE:
            self.setWindowTitle(f"脚本内容 - {self.file_name}" if self.file_name else "脚本内容")
            self.resize(800, 600)
        else:
            self.setWindowTitle(f"脚本内容 - {self.file_name}" if self.file_name else "脚本内容")
            self.resize(800, 600)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 标题
        if FLUENT_WIDGETS_AVAILABLE:
            title_label = SubtitleLabel(
                f"脚本文件: {self.file_name}" if self.file_name else "脚本内容",
                self
            )
        else:
            from PySide6.QtWidgets import QLabel
            title_label = QLabel(
                f"脚本文件: {self.file_name}" if self.file_name else "脚本内容",
                self
            )
            title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        
        layout.addWidget(title_label)
        
        # 脚本内容显示区域
        self.text_edit = TextEdit(self) if FLUENT_WIDGETS_AVAILABLE else QTextEdit(self)
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlainText(self.script_content)
        layout.addWidget(self.text_edit)
        
        # 关闭按钮
        if FLUENT_WIDGETS_AVAILABLE:
            btn_close = PushButton("关闭", self)
        else:
            from PySide6.QtWidgets import QPushButton
            btn_close = QPushButton("关闭", self)
        
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

