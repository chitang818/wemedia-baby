"""
飞书授权对话框
文件路径：src/proprietary/ui/pages/material/feishu_auth_dialog.py
功能：提供飞书授权的交互界面，展示授权指引、状态和操作按钮
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QProgressBar,
)
from PySide6.QtCore import Qt, QTimer, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap, QImage

from qfluentwidgets import (
    SubtitleLabel,
    BodyLabel,
    PrimaryPushButton,
    PushButton,
    LineEdit,
    HyperlinkButton,
    InfoBarIcon,
    FluentIcon as FIF,
)

from src.ui.components.base_dialog import StandardBaseDialog

logger = logging.getLogger(__name__)


class FeishuAuthDialog(StandardBaseDialog):
    """飞书授权对话框

    交互流程：
    1. 显示授权说明和「去授权」按钮
    2. 用户点击后打开浏览器跳转飞书授权页
    3. 等待本地回调服务器接收授权结果
    4. 授权成功显示用户信息和完成按钮
    """

    auth_success = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent, title="飞书授权")
        self.widget.setMinimumWidth(480)
        self.widget.setMinimumHeight(380)

        self._auth_task = None
        self._authorized = False

        self._build_ui()
        self._check_initial_status()

        self.set_yes_button_text("完成")
        self.set_cancel_button_text("关闭")

    def _build_ui(self):
        """构建授权界面"""
        layout = QVBoxLayout()
        layout.setSpacing(16)

        # 状态图标区
        self._status_icon = BodyLabel("🔐", self.widget)
        self._status_icon.setStyleSheet("font-size: 48px;")
        self._status_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status_icon)

        # 状态标题
        self._title_label = SubtitleLabel("连接飞书账号", self.widget)
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._title_label)

        # 状态描述
        self._desc_label = BodyLabel(
            "授权后可直接从飞书表格同步文案数据到本地文案库，\n支持多人协作共享文案。",
            self.widget,
        )
        self._desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._desc_label.setWordWrap(True)
        self._desc_label.setTextColor("#646a73", "#646a73")
        layout.addWidget(self._desc_label)

        # 进度条（授权中显示）
        self._progress_bar = QProgressBar(self.widget)
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setVisible(False)
        self._progress_bar.setFixedHeight(4)
        self._progress_bar.setTextVisible(False)
        layout.addWidget(self._progress_bar)

        # 用户信息区（授权成功后显示）
        self._user_info_widget = QWidget(self.widget)
        user_layout = QVBoxLayout(self._user_info_widget)
        user_layout.setContentsMargins(0, 0, 0, 0)
        user_layout.setSpacing(8)

        self._user_name_label = BodyLabel("", self._user_info_widget)
        self._user_name_label.setStyleSheet(
            "font-size: 16px; font-weight: 600; color: #1f2329;"
        )
        self._user_name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        user_layout.addWidget(self._user_name_label)

        self._user_hint_label = BodyLabel("", self._user_info_widget)
        self._user_hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._user_hint_label.setTextColor("#646a73", "#646a73")
        user_layout.addWidget(self._user_hint_label)

        self._user_info_widget.setVisible(False)
        layout.addWidget(self._user_info_widget)

        # 授权链接显示区（授权中显示，供手动复制）
        self._auth_url_widget = QWidget(self.widget)
        url_layout = QVBoxLayout(self._auth_url_widget)
        url_layout.setContentsMargins(0, 0, 0, 0)
        url_layout.setSpacing(6)

        self._auth_url_label = BodyLabel("授权链接：", self._auth_url_widget)
        self._auth_url_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        url_layout.addWidget(self._auth_url_label)

        self._auth_url_edit = LineEdit(self._auth_url_widget)
        self._auth_url_edit.setReadOnly(True)
        self._auth_url_edit.setPlaceholderText("授权链接将在此显示")
        url_layout.addWidget(self._auth_url_edit)

        self._copy_url_btn = PushButton("复制链接", self._auth_url_widget)
        self._copy_url_btn.clicked.connect(self._on_copy_url_clicked)
        self._copy_url_btn.setFixedWidth(100)
        copy_layout = QHBoxLayout()
        copy_layout.addStretch(1)
        copy_layout.addWidget(self._copy_url_btn)
        copy_layout.addStretch(1)
        url_layout.addLayout(copy_layout)

        self._auth_url_widget.setVisible(False)
        layout.addWidget(self._auth_url_widget)

        # 操作按钮区
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self._auth_button = PrimaryPushButton("前往飞书授权", self.widget)
        self._auth_button.clicked.connect(self._on_auth_clicked)
        btn_layout.addWidget(self._auth_button)

        self._revoke_button = PushButton("解除授权", self.widget)
        self._revoke_button.clicked.connect(self._on_revoke_clicked)
        self._revoke_button.setVisible(False)
        btn_layout.addWidget(self._revoke_button)

        btn_layout.addStretch(1)
        layout.addLayout(btn_layout)

        # 安全说明
        self._security_hint = BodyLabel(
            "🔒 授权数据加密存储在本地，仅用于读取飞书表格数据，不会上传您的任何信息。",
            self.widget,
        )
        self._security_hint.setWordWrap(True)
        self._security_hint.setTextColor("#999999", "#999999")
        self._security_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._security_hint)

        layout.addStretch(1)
        self.viewLayout.addLayout(layout)

    def _check_initial_status(self):
        """检查初始授权状态"""
        from src.ui.utils.async_helper import run_async_from_ui

        async def _check():
            try:
                from src.proprietary.services.feishu.feishu_auth_service import (
                    FeishuAuthService,
                )

                auth = FeishuAuthService.get_instance()
                if not auth.is_app_configured():
                    self._show_app_not_configured()
                    return

                authorized = await auth.is_authorized(verify=False)
                if authorized:
                    user_info = auth.get_user_info()
                    if user_info and user_info.name:
                        self._show_authorized_state(user_info.name)
                    else:
                        user_info = await auth.fetch_user_info()
                        if user_info:
                            self._show_authorized_state(user_info.name)
                        else:
                            self._show_unauthorized_state()
                else:
                    self._show_unauthorized_state()
            except Exception as e:
                logger.debug("检查飞书授权状态失败: %s", e)
                self._show_unauthorized_state()

        run_async_from_ui(_check)

    def _show_unauthorized_state(self):
        """未授权状态"""
        self._status_icon.setText("🔐")
        self._title_label.setText("连接飞书账号")
        self._desc_label.setText(
            "授权后可直接从飞书表格同步文案数据到本地文案库，\n支持多人协作共享文案。"
        )
        self._auth_button.setVisible(True)
        self._auth_button.setEnabled(True)
        self._auth_button.setText("前往飞书授权")
        self._revoke_button.setVisible(False)
        self._progress_bar.setVisible(False)
        self._user_info_widget.setVisible(False)
        self._auth_url_widget.setVisible(False)
        self.yesButton.setEnabled(True)

    def _show_authorized_state(self, user_name: str):
        """已授权状态"""
        self._status_icon.setText("✅")
        self._title_label.setText("飞书账号已连接")
        self._desc_label.setVisible(False)
        self._auth_button.setVisible(False)
        self._revoke_button.setVisible(True)
        self._progress_bar.setVisible(False)
        self._user_info_widget.setVisible(True)
        self._auth_url_widget.setVisible(False)
        self._user_name_label.setText(user_name)
        self._user_hint_label.setText("已成功授权，可以选择飞书表格进行文案同步")
        self._authorized = True
        self.auth_success.emit()

    def _show_authing_state(self, auth_url: str = ""):
        """授权中状态"""
        self._status_icon.setText("⏳")
        self._title_label.setText("正在授权...")
        self._desc_label.setText("请在浏览器中完成飞书授权，授权成功后此页面将自动更新。")
        self._auth_button.setEnabled(False)
        self._auth_button.setText("授权中...")
        self._revoke_button.setVisible(False)
        self._progress_bar.setVisible(True)
        self._user_info_widget.setVisible(False)

        if auth_url:
            self._auth_url_widget.setVisible(True)
            self._auth_url_edit.setText(auth_url)
        else:
            self._auth_url_widget.setVisible(False)

    def _show_app_not_configured(self):
        """应用未配置状态"""
        self._status_icon.setText("⚠️")
        self._title_label.setText("飞书应用未配置")
        self._desc_label.setText(
            "请先在 config/feishu_config.json 中配置飞书应用的 app_id 和 app_secret。\n"
            "配置完成后重启软件即可使用飞书同步功能。"
        )
        self._auth_button.setVisible(False)
        self._revoke_button.setVisible(False)
        self._progress_bar.setVisible(False)
        self._user_info_widget.setVisible(False)

    def _on_auth_clicked(self):
        """点击授权按钮"""
        from src.ui.utils.async_helper import run_async_from_ui

        async def _do_auth():
            try:
                from src.proprietary.services.feishu.feishu_auth_service import (
                    FeishuAuthService,
                )

                auth = FeishuAuthService.get_instance()

                auth_url, state = "", ""
                try:
                    auth_url, state = auth.get_auth_url()
                except Exception:
                    pass

                self._show_authing_state(auth_url)

                if auth_url:
                    try:
                        QDesktopServices.openUrl(QUrl(auth_url))
                    except Exception:
                        pass

                success, message = await auth.start_auth_flow(
                    open_browser=False, expected_state=state
                )

                if success:
                    user_info = await auth.fetch_user_info()
                    user_name = user_info.name if user_info else ""
                    self._show_authorized_state(user_name)
                else:
                    self._show_unauthorized_state()
                    self._title_label.setText("授权失败")
                    self._desc_label.setText(message)

            except Exception as e:
                logger.error("飞书授权异常: %s", e, exc_info=True)
                self._show_unauthorized_state()
                self._title_label.setText("授权出错")
                self._desc_label.setText(f"授权过程中发生错误：{e}")

        run_async_from_ui(_do_auth)

    def _on_copy_url_clicked(self):
        """复制授权链接"""
        from PySide6.QtWidgets import QApplication
        url = self._auth_url_edit.text()
        if url:
            QApplication.clipboard().setText(url)
            from qfluentwidgets import InfoBar, InfoBarPosition
            InfoBar.success(
                title="复制成功",
                content="授权链接已复制到剪贴板，请在浏览器中打开",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                duration=3000,
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_revoke_clicked(self):
        """解除授权"""
        from src.ui.utils.async_helper import run_async_from_ui
        from qfluentwidgets import MessageBox

        confirm = MessageBox(
            "确认解除授权",
            "解除后将无法从飞书同步文案数据，确定要解除吗？",
            self,
        )
        if not confirm.exec():
            return

        async def _do_revoke():
            try:
                from src.proprietary.services.feishu.feishu_auth_service import (
                    FeishuAuthService,
                )

                auth = FeishuAuthService.get_instance()
                await auth.revoke_auth()
                self._authorized = False
                self._show_unauthorized_state()
            except Exception as e:
                logger.error("解除授权失败: %s", e)

        run_async_from_ui(_do_revoke)

    def is_authorized(self) -> bool:
        return self._authorized

    def closeEvent(self, event):
        if self._auth_task and not self._auth_task.done():
            self._auth_task.cancel()
        super().closeEvent(event)
