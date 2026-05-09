"""
认证组件
文件路径：src/ui/auth/auth_widget.py
功能：登录注册界面（已实现，使用LoginDialog）
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, Signal
import logging

logger = logging.getLogger(__name__)


class AuthWidget(QWidget):
    """认证组件"""
    
    # 登录成功信号
    login_success = Signal(dict)  # 传递user_info
    
    def __init__(self, parent=None):
        """初始化认证组件"""
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 欢迎标签
        welcome_label = QLabel("欢迎使用媒小宝")
        welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_label.setStyleSheet("font-size: 24px; font-weight: bold; margin: 20px;")
        layout.addWidget(welcome_label)
        
        # 登录按钮
        btn_login = QPushButton("登录")
        btn_login.setMinimumSize(200, 40)
        btn_login.clicked.connect(self._show_login_dialog)
        layout.addWidget(btn_login)
        
        # 提示标签
        tip_label = QLabel("点击上方按钮登录，或使用菜单中的登录功能")
        tip_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tip_label.setStyleSheet("color: gray; margin-top: 20px;")
        layout.addWidget(tip_label)
    
    def _show_login_dialog(self):
        """显示登录对话框"""
        try:
            from ..dialogs.login_dialog import LoginDialog
            
            dialog = LoginDialog(self)
            dialog.login_success.connect(self.login_success.emit)
            dialog.exec()
        except Exception as e:
            logger.error(f"显示登录对话框失败: {e}", exc_info=True)

