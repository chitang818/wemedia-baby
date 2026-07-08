"""
飞书表格绑定对话框
文件路径：src/proprietary/ui/pages/material/feishu_sheet_picker_dialog.py
功能：提供极简的飞书表格绑定交互界面
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from PySide6.QtCore import Qt

from qfluentwidgets import (
    SubtitleLabel,
    BodyLabel,
    LineEdit,
    PushButton,
    HyperlinkButton,
    FluentIcon as FIF,
    IconWidget,
    MessageBox,
)

from src.ui.components.base_dialog import StandardBaseDialog

logger = logging.getLogger(__name__)


class FeishuSheetPickerDialog(StandardBaseDialog):
    """飞书表格绑定对话框

    交互流程：
    1. 极简的输入表格链接。
    2. 下方附带当前登录的飞书账号信息，并提供一键解绑功能。
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent, title="绑定飞书表格")
        self.widget.setMinimumWidth(500)
        
        self._spreadsheet_token = ""
        self._spreadsheet_name = ""

        self._build_ui()

        self.set_yes_button_text("开始绑定")
        self.set_cancel_button_text("取消")
        self.yesButton.setEnabled(False)

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(24)

        # 1. 链接输入区
        input_area = self._build_input_area()
        layout.addWidget(input_area)

        # 2. 底部轻量的账号信息
        user_info_bar = self._build_user_info_bar()
        layout.addWidget(user_info_bar)

        layout.addStretch(1)
        self.viewLayout.addLayout(layout)

    def _build_input_area(self) -> QWidget:
        widget = QWidget(self.widget)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = SubtitleLabel("输入飞书表格链接", widget)
        layout.addWidget(title)

        url_layout = QHBoxLayout()
        url_layout.setSpacing(8)

        self._url_edit = LineEdit(widget)
        self._url_edit.setPlaceholderText("例如：https://xxx.feishu.cn/sheets/shtabc123")
        self._url_edit.textChanged.connect(self._on_url_changed)
        url_layout.addWidget(self._url_edit)

        self._parse_btn = PushButton("解析", widget)
        self._parse_btn.clicked.connect(self._on_parse_clicked)
        self._parse_btn.setFixedWidth(80)
        self._parse_btn.setEnabled(False)
        url_layout.addWidget(self._parse_btn)

        layout.addLayout(url_layout)

        self._url_hint = BodyLabel("", widget)
        self._url_hint.setTextColor("#999999", "#999999")
        self._url_hint.setWordWrap(True)
        layout.addWidget(self._url_hint)

        return widget

    def _build_user_info_bar(self) -> QWidget:
        widget = QWidget(self.widget)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        try:
            from src.proprietary.services.feishu.feishu_auth_service import FeishuAuthService
            auth = FeishuAuthService.get_instance()
            user_info = auth.get_user_info()
            if user_info and user_info.name:
                name_text = user_info.name
            else:
                name_text = "已授权飞书"
        except Exception:
            name_text = "已授权飞书"

        icon = IconWidget(FIF.CHECKBOX, widget)
        icon.setFixedSize(16, 16)
        
        label = BodyLabel(f"当前授权账号：{name_text}", widget)
        label.setTextColor("#00b42a", "#00b42a") # 绿色
        
        unbind_btn = HyperlinkButton("", "解除绑定", widget)
        unbind_btn.clicked.connect(self._on_unbind_clicked)
        
        layout.addWidget(icon)
        layout.addSpacing(4)
        layout.addWidget(label)
        layout.addStretch(1)
        layout.addWidget(unbind_btn)
        
        return widget

    def _on_unbind_clicked(self):
        w = MessageBox(
            "解除飞书授权",
            "确定要解除当前飞书账号的授权吗？解绑后若需同步飞书，需要重新扫码登录。",
            self
        )
        if w.exec():
            # 执行清理逻辑
            try:
                from src.proprietary.services.feishu.feishu_auth_service import FeishuAuthService
                auth = FeishuAuthService.get_instance()
                auth._access_token = ""
                auth._refresh_token = ""
                auth._user_info = None
                auth._clear_tokens_from_storage()
            except Exception as e:
                logger.error(f"清理飞书授权失败: {e}")
            
            # 关闭弹窗，让用户在外层重新点击绑定走完整的授权流程
            self.reject()

    def _on_url_changed(self, text: str):
        has_text = bool(text.strip())
        self._parse_btn.setEnabled(has_text)
        self.yesButton.setEnabled(False)
        self._url_hint.setText("")

    def _on_parse_clicked(self):
        """解析表格链接"""
        url = self._url_edit.text().strip()
        if not url:
            return

        from src.proprietary.services.feishu.feishu_sheets_client import FeishuSheetsClient
        token = FeishuSheetsClient.parse_spreadsheet_token(url)
        
        if not token:
            self._url_hint.setText("❌ 无法识别表格链接，请检查格式")
            self._url_hint.setTextColor("#f53f3f", "#f53f3f")
            self.yesButton.setEnabled(False)
            return

        self._spreadsheet_token = token
        
        # 尝试异步获取 spreadsheet 名字
        from src.ui.utils.async_helper import run_async_from_ui
        self._parse_btn.setEnabled(False)
        self._parse_btn.setText("验证中...")

        async def _verify_token():
            client = None
            try:
                client = FeishuSheetsClient()
                info = await client.get_spreadsheet(token)
                self._spreadsheet_name = info.title
                self._url_hint.setText(f"✅ 解析成功：{info.title} (将绑定其下所有可见子表)")
                self._url_hint.setTextColor("#00b42a", "#00b42a")
                self.yesButton.setEnabled(True)
            except Exception as e:
                self._url_hint.setText(f"⚠️ 链接有效，但读取失败，可能是未给应用授权该表格文档: {e}")
                self._url_hint.setTextColor("#ff7d00", "#ff7d00")
                self.yesButton.setEnabled(True)
            finally:
                if client:
                    await client.close()
                self._parse_btn.setEnabled(True)
                self._parse_btn.setText("解析")
                
        run_async_from_ui(_verify_token)

    def get_result(self) -> Dict[str, Any]:
        """获取选择结果"""
        return {
            "spreadsheet_token": self._spreadsheet_token,
            "spreadsheet_name": self._spreadsheet_name,
        }
