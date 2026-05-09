"""
密码重置对话框
文件路径：src/ui/dialogs/password_reset_dialog.py
功能：密码重置界面，使用 PySide6-Fluent-Widgets 组件
"""

from typing import Optional
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget
from PySide6.QtCore import Qt
import logging

# 导入 PySide6-Fluent-Widgets 组件
try:
    from qfluentwidgets import (
        BodyLabel, CaptionLabel,
        LineEdit, PasswordLineEdit, PrimaryPushButton, PushButton,
        InfoBar, InfoBarPosition, StrongBodyLabel
    )
    from src.ui.components.base_dialog import AppMessageBoxBase
    FLUENT_WIDGETS_AVAILABLE = True
except ImportError:
    FLUENT_WIDGETS_AVAILABLE = False
    AppMessageBoxBase = QWidget  # type: ignore[misc, assignment]

logger = logging.getLogger(__name__)


class PasswordResetDialog(AppMessageBoxBase if FLUENT_WIDGETS_AVAILABLE else QWidget):
    """密码重置对话框 - 使用 PySide6-Fluent-Widgets MessageBoxBase"""
    
    def __init__(self, parent: Optional[QWidget] = None):
        """初始化密码重置对话框"""
        if FLUENT_WIDGETS_AVAILABLE:
            super().__init__(parent, header_title="重置密码")
        else:
            super().__init__(parent)
        self.user_auth = None
        self._init_services()
        self._setup_ui()
    
    def _init_services(self):
        """初始化服务"""
        try:
            from src.services.auth import UserAuth
            
            self.user_auth = UserAuth()
            logger.debug("密码重置服务初始化成功")
        except Exception as e:
            logger.warning(f"初始化密码重置服务失败: {e}")
    
    def _setup_ui(self):
        """设置UI"""
        if not FLUENT_WIDGETS_AVAILABLE:
            return
        
        # 设置对话框大小
        self.widget.setMinimumWidth(420)
        
        # 说明文字
        desc = BodyLabel(
            "请输入您的用户名和注册邮箱，我们将为您重置密码。",
            self.widget
        )
        desc.setWordWrap(True)
        desc.setTextColor(Qt.GlobalColor.gray, Qt.GlobalColor.gray)
        self.viewLayout.addWidget(desc)
        
        self.viewLayout.addSpacing(16)
        
        # 用户名输入
        self.username_input = LineEdit(self.widget)
        self.username_input.setPlaceholderText("用户名")
        self.username_input.setClearButtonEnabled(True)
        self.viewLayout.addWidget(self.username_input)
        
        self.viewLayout.addSpacing(10)
        
        # 邮箱输入
        self.email_input = LineEdit(self.widget)
        self.email_input.setPlaceholderText("注册邮箱")
        self.email_input.setClearButtonEnabled(True)
        self.viewLayout.addWidget(self.email_input)
        
        self.viewLayout.addSpacing(16)
        
        # 分隔标题
        new_pwd_label = StrongBodyLabel("设置新密码", self.widget)
        self.viewLayout.addWidget(new_pwd_label)
        
        self.viewLayout.addSpacing(8)
        
        # 新密码输入
        self.password_input = PasswordLineEdit(self.widget)
        self.password_input.setPlaceholderText("新密码（8-20位）")
        self.viewLayout.addWidget(self.password_input)
        
        self.viewLayout.addSpacing(10)
        
        # 确认新密码输入
        self.confirm_password_input = PasswordLineEdit(self.widget)
        self.confirm_password_input.setPlaceholderText("确认新密码")
        self.viewLayout.addWidget(self.confirm_password_input)
        
        self.viewLayout.addSpacing(16)
        
        # 设置按钮文字
        self.yesButton.setText("重置密码")
        self.cancelButton.setText("取消")
        
        # 绑定重置按钮
        self.yesButton.clicked.disconnect()
        self.yesButton.clicked.connect(self._on_reset)
        
        # 按钮排序：取消在左，确定在右
        self._reorder_buttons()
        
        # 回车键重置
        self.confirm_password_input.returnPressed.connect(self._on_reset)

    def _reorder_buttons(self):
        button_layout = getattr(self, "buttonLayout", None)
        if button_layout is None:
            button_layout = self.buttonGroup.layout()
        if button_layout:
            button_layout.removeWidget(self.yesButton)
            button_layout.removeWidget(self.cancelButton)
            button_layout.addWidget(self.cancelButton)
            button_layout.addWidget(self.yesButton)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            reject = getattr(self, "reject", None)
            if callable(reject):
                reject()
            else:
                self.close()
            return
        super().keyPressEvent(event)

    def _validate_input(self) -> tuple[bool, str]:
        """验证输入
        
        Returns:
            (是否有效, 错误信息)
        """
        username = self.username_input.text().strip()
        email = self.email_input.text().strip()
        password = self.password_input.text()
        confirm_password = self.confirm_password_input.text()
        
        if not username:
            self.username_input.setFocus()
            return False, "请输入用户名"
        
        if not email:
            self.email_input.setFocus()
            return False, "请输入邮箱"
        
        if '@' not in email or '.' not in email:
            self.email_input.setFocus()
            return False, "请输入有效的邮箱地址"
        
        if not password:
            self.password_input.setFocus()
            return False, "请输入新密码"
        
        if len(password) < 8 or len(password) > 20:
            self.password_input.setFocus()
            return False, "密码长度应为8-20位"
        
        if password != confirm_password:
            self.confirm_password_input.clear()
            self.confirm_password_input.setFocus()
            return False, "两次输入的密码不一致"
        
        return True, ""
    
    def _on_reset(self):
        """处理密码重置"""
        # 验证输入
        valid, error_msg = self._validate_input()
        if not valid:
            InfoBar.warning(
                title="输入错误",
                content=error_msg,
                duration=2000,
                parent=self
            )
            return
        
        username = self.username_input.text().strip()
        email = self.email_input.text().strip()
        password = self.password_input.text()
        
        if not self.user_auth:
            # 如果服务未初始化，模拟重置成功（开发模式）
            logger.warning("密码重置服务未初始化，使用模拟重置")
            InfoBar.success(
                title="密码重置成功",
                content="密码已重置，请使用新密码登录（开发模式）",
                duration=2000,
                parent=self
            )
            self.accept()
            return
        
        # 使用 AsyncWorker 在独立线程执行，避免 qasync 下 "Event loop already running" 错误
        from ..utils.async_helper import AsyncWorker

        async def do_reset():
            success = await self.user_auth.reset(username, email, password)
            if success:
                return {'success': True}
            return {'success': False, 'message': '重置失败，请检查用户名和邮箱'}

        worker = AsyncWorker(do_reset)
        worker.setParent(self)

        def on_finished(result):
            if result and result.get('success'):
                InfoBar.success(
                    title="密码重置成功",
                    content="密码已重置，请使用新密码登录",
                    duration=2000,
                    parent=self
                )
                self.accept()
            else:
                InfoBar.error(
                    title="重置失败",
                    content=result.get('message', '密码重置失败，请检查用户名和邮箱') if result else '密码重置失败',
                    duration=3000,
                    parent=self
                )

        def on_error(err_msg):
            logger.error("密码重置失败: %s", err_msg)
            InfoBar.error(
                title="重置失败",
                content=err_msg or "密码重置出错",
                duration=3000,
                parent=self
            )

        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        worker.start()
