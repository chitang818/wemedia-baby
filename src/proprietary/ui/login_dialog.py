"""
登录对话框（闭源实现）
原路径：src/ui/dialogs/login_dialog.py
"""

from typing import Optional
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget
from PySide6.QtCore import Qt, Signal
import logging

try:
    from qfluentwidgets import (
        BodyLabel,
        LineEdit,
        PasswordLineEdit,
        PrimaryPushButton,
        PushButton,
        CheckBox,
        InfoBar,
        InfoBarPosition,
        FluentIcon,
        CardWidget,
    )
    from src.ui.components.base_dialog import AppMessageBoxBase

    FLUENT_WIDGETS_AVAILABLE = True
except ImportError:
    FLUENT_WIDGETS_AVAILABLE = False
    from PySide6.QtWidgets import QDialog

    AppMessageBoxBase = QWidget  # type: ignore[misc, assignment]

logger = logging.getLogger(__name__)


class LoginDialog(AppMessageBoxBase if FLUENT_WIDGETS_AVAILABLE else QWidget):
    """登录对话框 - 使用 PySide6-Fluent-Widgets MessageBoxBase"""

    login_success = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None):
        if FLUENT_WIDGETS_AVAILABLE:
            super().__init__(parent, header_title="登录")
        else:
            super().__init__(parent)
        self.user_auth = None
        self._user_info = None
        self._init_services()
        self._setup_ui()

    def _init_services(self):
        try:
            from src.services.auth import UserAuth

            self.user_auth = UserAuth()
            logger.debug("登录服务初始化成功")
        except Exception as e:
            logger.warning(f"初始化登录服务失败: {e}")

    def _setup_ui(self):
        if not FLUENT_WIDGETS_AVAILABLE:
            return

        self.widget.setMinimumWidth(400)

        desc = BodyLabel("请输入您的账号和密码", self.widget)
        desc.setTextColor(Qt.GlobalColor.gray, Qt.GlobalColor.gray)
        self.viewLayout.addWidget(desc)

        self.viewLayout.addSpacing(16)

        self.username_input = LineEdit(self.widget)
        self.username_input.setPlaceholderText("用户名（3-20位字母、数字或下划线）")
        self.username_input.setClearButtonEnabled(True)
        self.viewLayout.addWidget(self.username_input)

        self.viewLayout.addSpacing(12)

        self.password_input = PasswordLineEdit(self.widget)
        self.password_input.setPlaceholderText("密码（8-20位）")
        self.viewLayout.addWidget(self.password_input)

        self.viewLayout.addSpacing(8)

        self.remember_checkbox = CheckBox("记住我（一直有效）", self.widget)
        self.viewLayout.addWidget(self.remember_checkbox)
        self._load_remember_me()

        self.viewLayout.addSpacing(16)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        btn_forgot = PushButton("忘记密码", self.widget)
        btn_forgot.clicked.connect(self._on_forgot_password)
        btn_layout.addWidget(btn_forgot)

        btn_register = PushButton("注册账号", self.widget)
        btn_register.clicked.connect(self._on_register)
        btn_layout.addWidget(btn_register)

        btn_layout.addStretch()
        self.viewLayout.addLayout(btn_layout)

        self.yesButton.setText("登录")
        self.cancelButton.setText("取消")

        self.yesButton.clicked.disconnect()
        self.yesButton.clicked.connect(self._on_login)

        self._reorder_buttons()

        self.password_input.returnPressed.connect(self._on_login)
        self.username_input.returnPressed.connect(lambda: self.password_input.setFocus())

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

    def _load_remember_me(self):
        try:
            from src.services.auth.auth_remember import get_remembered_credentials

            remembered, username, password = get_remembered_credentials()
            if remembered and username:
                self.remember_checkbox.setChecked(True)
                self.username_input.setText(username)
                if password:
                    self.password_input.setText(password)
        except Exception as e:
            logger.debug("加载记住我失败: %s", e)

    def _on_login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()
        remember_me = self.remember_checkbox.isChecked()

        if not username:
            InfoBar.warning(title="输入错误", content="请输入用户名", duration=2000, parent=self)
            self.username_input.setFocus()
            return

        if not password:
            InfoBar.warning(title="输入错误", content="请输入密码", duration=2000, parent=self)
            self.password_input.setFocus()
            return

        if not self.user_auth:
            logger.warning("登录服务未初始化，使用模拟登录")
            try:
                from src.services.auth.auth_remember import save_remember_me, clear_remember_me

                if remember_me:
                    save_remember_me(username, password)
                else:
                    clear_remember_me()
            except Exception as e:
                logger.debug("保存/清除记住我失败: %s", e)
            from src.services.auth import CurrentUserService

            CurrentUserService().set_user(1, username, level="vip0", is_expired=True)
            self._user_info = {"id": 1, "username": username, "email": f"{username}@example.com", "role": "user"}
            InfoBar.success(title="登录成功", content=f"欢迎，{username}！（开发模式）", duration=2000, parent=self)
            self.login_success.emit(self._user_info)
            self.accept()
            return

        from src.ui.utils.async_helper import AsyncWorker

        async def do_login():
            user_info = await self.user_auth.login(username, password)
            if user_info:
                return {"success": True, "user_info": user_info}
            msg = getattr(self.user_auth, "last_error_message", None) or "用户名或密码错误"
            return {"success": False, "message": msg}

        worker = AsyncWorker(do_login)
        worker.setParent(self)

        def on_finished(result):
            if result and result.get("success"):
                self._user_info = result.get("user_info", {})
                try:
                    from src.services.auth.auth_remember import save_remember_me, clear_remember_me

                    if remember_me:
                        save_remember_me(username, password)
                    else:
                        clear_remember_me()
                except Exception as e:
                    logger.debug("保存/清除记住我失败: %s", e)
                InfoBar.success(title="登录成功", content=f"欢迎回来，{username}！", duration=2000, parent=self)
                self.login_success.emit(self._user_info)
                self.accept()
            else:
                InfoBar.error(
                    title="登录失败",
                    content=result.get("message", "用户名或密码错误") if result else "用户名或密码错误",
                    duration=3000,
                    parent=self,
                )
                self.password_input.clear()
                self.password_input.setFocus()

        def on_error(err_msg):
            logger.error("登录失败: %s", err_msg)
            InfoBar.error(title="登录失败", content=err_msg or "登录出错", duration=3000, parent=self)
            self.password_input.clear()
            self.password_input.setFocus()

        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        worker.start()

    def _on_register(self):
        try:
            from .register_dialog import RegisterDialog

            self.hide()
            register_dialog = RegisterDialog(self.parent())
            if register_dialog.exec():
                if hasattr(register_dialog, "get_username"):
                    self.username_input.setText(register_dialog.get_username())
                self.password_input.setFocus()
            self.show()
        except Exception as e:
            logger.error(f"打开注册对话框失败: {e}")

    def _on_forgot_password(self):
        try:
            from .password_reset_dialog import PasswordResetDialog

            self.hide()
            reset_dialog = PasswordResetDialog(self.parent())
            reset_dialog.exec()
            self.show()
        except Exception as e:
            logger.error(f"打开密码重置对话框失败: {e}")

    def get_user_info(self) -> Optional[dict]:
        return self._user_info

