"""
工作台组件
文件路径：src/ui/workspace/workspace_widget.py
功能：工作台主界面
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt
import logging

logger = logging.getLogger(__name__)


class WorkspaceWidget(QWidget):
    """工作台组件"""
    
    def __init__(self, parent=None):
        """初始化工作台组件"""
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """设置UI"""
        layout = QVBoxLayout(self)
        
        # 占位标签
        label = QLabel("工作台（待实现）")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

