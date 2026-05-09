"""
注册对话框
文件路径：src/ui/dialogs/register_dialog.py
功能：用户注册界面，使用 PySide6-Fluent-Widgets 组件
"""

from typing import Optional
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget
from PySide6.QtCore import Qt
import logging

# 导入 PySide6-Fluent-Widgets 组件
try:
    from qfluentwidgets import (
        BodyLabel, LineEdit, PasswordLineEdit,
        PrimaryPushButton, PushButton, InfoBar, InfoBarPosition
    )
    from src.ui.components.base_dialog import AppMessageBoxBase
    FLUENT_WIDGETS_AVAILABLE = True
except ImportError:
    FLUENT_WIDGETS_AVAILABLE = False
    from PySide6.QtWidgets import QWidget
    AppMessageBoxBase = QWidget  # type: ignore[misc, assignment]

logger = logging.getLogger(__name__)

if FLUENT_WIDGETS_AVAILABLE:
    class RegisterSuccessMessageBox(AppMessageBoxBase):
        """注册成功提示框，与登录/注册弹窗同风格（Fluent）"""
        def __init__(self, parent: Optional[QWidget] = None):
            super().__init__(parent, header_title="提示")
            self.widget.setMinimumWidth(360)
            self.viewLayout.addSpacing(8)
            content = BodyLabel("账号注册成功", self.widget)
            self.viewLayout.addWidget(content)
            self.yesButton.setText("确定")
            self.cancelButton.hide()
            self.yesButton.clicked.connect(self.accept)

else:
    RegisterSuccessMessageBox = None  # type: ignore[misc, assignment]


class RegisterDialog(AppMessageBoxBase if FLUENT_WIDGETS_AVAILABLE else QWidget):
    """注册对话框 - 使用 PySide6-Fluent-Widgets MessageBoxBase"""
    
    def __init__(self, parent: Optional[QWidget] = None):
        """初始化注册对话框"""
        if FLUENT_WIDGETS_AVAILABLE:
            super().__init__(parent, header_title="创建账号")
        else:
            super().__init__(parent)
        self.user_auth = None
        self._username = None
        self._init_services()
        self._setup_ui()
    
    def _init_services(self):
        """初始化服务"""
        try:
            from src.services.auth import UserAuth
            
            self.user_auth = UserAuth()
            logger.debug("注册服务初始化成功")
        except Exception as e:
            logger.warning(f"初始化注册服务失败: {e}")
    
    def _setup_ui(self):
        """设置UI"""
        if not FLUENT_WIDGETS_AVAILABLE:
            return
        
        # 设置对话框大小
        self.widget.setMinimumWidth(420)
        
        # 说明文字
        desc = BodyLabel("请填写以下信息完成注册", self.widget)
        desc.setTextColor(Qt.GlobalColor.gray, Qt.GlobalColor.gray)
        self.viewLayout.addWidget(desc)
        
        self.viewLayout.addSpacing(16)
        
        # 用户名输入
        self.username_input = LineEdit(self.widget)
        self.username_input.setPlaceholderText("用户名（3-20位字母、数字或下划线）")
        self.username_input.setClearButtonEnabled(True)
        self.viewLayout.addWidget(self.username_input)
        
        self.viewLayout.addSpacing(10)
        
        # 邮箱输入
        self.email_input = LineEdit(self.widget)
        self.email_input.setPlaceholderText("邮箱地址")
        self.email_input.setClearButtonEnabled(True)
        self.viewLayout.addWidget(self.email_input)
        
        self.viewLayout.addSpacing(10)
        
        # 手机号（可选）
        self.phone_input = LineEdit(self.widget)
        self.phone_input.setPlaceholderText("手机号（选填）")
        self.phone_input.setClearButtonEnabled(True)
        self.viewLayout.addWidget(self.phone_input)
        
        self.viewLayout.addSpacing(10)
        
        # 密码输入
        self.password_input = PasswordLineEdit(self.widget)
        self.password_input.setPlaceholderText("密码（8-20位，含字母+数字+特殊符号）")
        self.viewLayout.addWidget(self.password_input)
        
        self.viewLayout.addSpacing(10)
        
        # 确认密码输入
        self.confirm_password_input = PasswordLineEdit(self.widget)
        self.confirm_password_input.setPlaceholderText("确认密码")
        self.viewLayout.addWidget(self.confirm_password_input)
        
        self.viewLayout.addSpacing(16)
        
        # 设置按钮文字
        self.yesButton.setText("注册")
        self.cancelButton.setText("取消")
        
        # 绑定注册按钮
        self.yesButton.clicked.disconnect()
        self.yesButton.clicked.connect(self._on_register)
        
        # 按钮排序：取消在左，确定在右
        self._reorder_buttons()
        
        # 回车键注册
        self.confirm_password_input.returnPressed.connect(self._on_register)

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
        
        if len(username) < 3 or len(username) > 20:
            self.username_input.setFocus()
            return False, "用户名长度应为3-20位"
        
        if not email:
            self.email_input.setFocus()
            return False, "请输入邮箱"
        
        if '@' not in email or '.' not in email:
            self.email_input.setFocus()
            return False, "请输入有效的邮箱地址"
        
        if not password:
            self.password_input.setFocus()
            return False, "请输入密码"
        
        if len(password) < 8 or len(password) > 20:
            self.password_input.setFocus()
            return False, "密码长度应为8-20位"
        
        if password != confirm_password:
            self.confirm_password_input.clear()
            self.confirm_password_input.setFocus()
            return False, "两次输入的密码不一致"
        
        return True, ""

    def _show_register_success_then_accept(self):
        """弹窗提示账号注册成功（与登录弹窗同风格），确定后关闭本对话框并回到登录界面"""
        if FLUENT_WIDGETS_AVAILABLE and RegisterSuccessMessageBox is not None:
            d = RegisterSuccessMessageBox(self)
            d.exec()
        else:
            from src.ui.utils.fluent_dialogs import show_info
            show_info(self, "提示", "账号注册成功")
        self.accept()
    
    def _on_register(self):
        """处理注册"""
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
            # 如果服务未初始化，模拟注册成功（开发模式）
            logger.warning("注册服务未初始化，使用模拟注册")
            self._username = username
            self._show_register_success_then_accept()
            return
        
        # 使用 AsyncWorker 在独立线程执行，避免 qasync 下 "Event loop already running" 错误
        from ..utils.async_helper import AsyncWorker

        phone = self.phone_input.text().strip() if getattr(self, "phone_input", None) else ""

        async def do_register():
            try:
                user_id = await self.user_auth.register(username, password, email, phone=phone or None)
                return {'success': True, 'user_id': user_id}
            except ValueError as e:
                return {'success': False, 'message': str(e)}
            except Exception as e:
                return {'success': False, 'message': f"注册失败: {str(e)}"}

        worker = AsyncWorker(do_register)
        worker.setParent(self)

        def on_finished(result):
            if result and result.get('success'):
                self._username = username
                self._show_register_success_then_accept()
            else:
                InfoBar.error(
                    title="注册失败",
                    content=result.get('message', '注册失败，请重试') if result else '注册失败',
                    duration=3000,
                    parent=self
                )

        def on_error(err_msg):
            logger.error("注册失败: %s", err_msg)
            InfoBar.error(
                title="注册失败",
                content=err_msg or "注册出错",
                duration=3000,
                parent=self
            )

        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        worker.start()
    
    def get_username(self) -> Optional[str]:
        """获取注册的用户名"""
        return self._username
