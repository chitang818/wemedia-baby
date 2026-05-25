"""
位置推广新建/编辑弹窗
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any

from PySide6.QtWidgets import QWidget, QFormLayout, QHBoxLayout
from PySide6.QtCore import Qt

from qfluentwidgets import LineEdit, BodyLabel

from src.ui.components.base_dialog import StandardBaseDialog
from src.ui.utils.fluent_tooltips import ToolTipPosition, apply_instructional_tooltip

logger = logging.getLogger(__name__)


class LocationPromotionEditDialog(StandardBaseDialog):
    """位置推广配置新建/编辑弹窗。"""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        item_data: Optional[Dict[str, Any]] = None,
    ):
        is_edit = item_data is not None
        title = "编辑位置配置" if is_edit else "新建位置配置"
        super().__init__(parent, title)

        self._accepting = False
        self._is_edit = is_edit
        self._item_data = item_data or {}

        self.widget.setMinimumWidth(560)
        self._build_form()

        if is_edit:
            self._fill_form(self._item_data)

        self.set_yes_button_text("保存")
        try:
            self.yesButton.clicked.connect(self.accept)
        except Exception:
            pass

    def _build_form(self):
        form_container = QWidget(self.widget)
        form_layout = QFormLayout(form_container)
        form_layout.setContentsMargins(0, 8, 0, 8)
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.edit_short_name = LineEdit(form_container)
        self.edit_short_name.setPlaceholderText(
            "请输入位置简称（唯一，不可修改）" if self._is_edit else "请输入位置简称（唯一）"
        )
        self.edit_short_name.setClearButtonEnabled(True)
        if self._is_edit:
            self.edit_short_name.setReadOnly(True)
            _lb_sn = BodyLabel("位置简称：", form_container)
            _lw_sn = QWidget(form_container)
            _h_sn = QHBoxLayout(_lw_sn)
            _h_sn.setContentsMargins(0, 0, 0, 0)
            _h_sn.setSpacing(4)
            _h_sn.addWidget(_lb_sn)
            apply_instructional_tooltip(
                "位置简称为唯一标识，编辑时不可修改",
                _lb_sn,
                self.edit_short_name,
                position=ToolTipPosition.TOP,
            )
            form_layout.addRow(_lw_sn, self.edit_short_name)
        else:
            form_layout.addRow(BodyLabel("位置简称：", form_container), self.edit_short_name)

        self.edit_douyin = LineEdit(form_container)
        self.edit_douyin.setPlaceholderText("抖音创作者页搜索该位置时输入的内容")
        self.edit_douyin.setClearButtonEnabled(True)
        form_layout.addRow(BodyLabel("抖音位置：", form_container), self.edit_douyin)

        self.edit_kuaishou = LineEdit(form_container)
        self.edit_kuaishou.setPlaceholderText("快手创作者页搜索该位置时输入的内容")
        self.edit_kuaishou.setClearButtonEnabled(True)
        form_layout.addRow(BodyLabel("快手位置：", form_container), self.edit_kuaishou)

        self.edit_channels = LineEdit(form_container)
        self.edit_channels.setPlaceholderText("视频号创作者页搜索该位置时输入的内容")
        self.edit_channels.setClearButtonEnabled(True)
        form_layout.addRow(BodyLabel("视频号位置：", form_container), self.edit_channels)

        self.edit_xiaohongshu = LineEdit(form_container)
        self.edit_xiaohongshu.setPlaceholderText("小红书创作者页搜索该位置时输入的内容")
        self.edit_xiaohongshu.setClearButtonEnabled(True)
        form_layout.addRow(BodyLabel("小红书位置：", form_container), self.edit_xiaohongshu)

        self.viewLayout.addWidget(form_container)

    def _fill_form(self, data: Dict[str, Any]):
        self.edit_short_name.setText(data.get("short_name") or "")
        self.edit_douyin.setText(data.get("douyin_location") or "")
        self.edit_kuaishou.setText(data.get("kuaishou_location") or "")
        self.edit_channels.setText(data.get("channels_location") or "")
        self.edit_xiaohongshu.setText(data.get("xiaohongshu_location") or "")

    def get_form_data(self) -> Dict[str, Any]:
        return {
            "short_name": self.edit_short_name.text().strip(),
            "douyin_location": self.edit_douyin.text().strip(),
            "kuaishou_location": self.edit_kuaishou.text().strip(),
            "channels_location": self.edit_channels.text().strip(),
            "xiaohongshu_location": self.edit_xiaohongshu.text().strip(),
        }

    def validate(self) -> Optional[str]:
        if not self.get_form_data()["short_name"]:
            return "位置简称不能为空，请填写后再保存。"
        return None

    def accept(self):
        if self._accepting:
            return
        self._accepting = True
        error = self.validate()
        if error:
            from qfluentwidgets import InfoBar, InfoBarPosition

            InfoBar.warning(
                title="提示",
                content=error,
                orient=Qt.Horizontal,
                isClosable=True,
                duration=4000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            self._accepting = False
            return
        try:
            super().accept()
        finally:
            self._accepting = False
