"""
购物车推广商品新建/编辑弹窗
文件路径：src/ui/pages/material/cart_promotion_edit_dialog.py
功能：提供商品配置表单弹窗，支持新建和编辑两种模式，包含商品简称、商品短标题与各平台链接/名称。
编辑模式下商品简称不可修改（唯一键，以避免唯一约束冲突）。
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any

from PySide6.QtWidgets import QWidget, QFormLayout, QHBoxLayout
from PySide6.QtCore import Qt

from qfluentwidgets import (
    LineEdit,
    BodyLabel,
)

from src.domain.publish.promotion_limits import CART_SHORT_TITLE_MAX_LEN
from src.ui.components.base_dialog import StandardBaseDialog
from src.ui.utils.fluent_tooltips import ToolTipPosition, apply_instructional_tooltip

logger = logging.getLogger(__name__)


class CartPromotionEditDialog(StandardBaseDialog):
    """购物车推广商品新建/编辑弹窗。

    Args:
        parent: 父控件。
        item_data: 传入现有商品字典时进入编辑模式；传入 None 时进入新建模式。
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        item_data: Optional[Dict[str, Any]] = None,
    ):
        is_edit = item_data is not None
        title = "编辑商品配置" if is_edit else "新建商品配置"
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

    # ---------- 表单构建 ----------

    def _build_form(self):
        """构建表单字段。"""
        form_container = QWidget(self.widget)
        form_layout = QFormLayout(form_container)
        form_layout.setContentsMargins(0, 8, 0, 8)
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # 商品简称（唯一键）
        self.edit_short_name = LineEdit(form_container)
        self.edit_short_name.setPlaceholderText("请输入商品简称（唯一，不可修改）" if self._is_edit else "请输入商品简称（唯一）")
        self.edit_short_name.setClearButtonEnabled(True)
        if self._is_edit:
            self.edit_short_name.setReadOnly(True)
            _lb_sn = BodyLabel("商品简称：", form_container)
            _lw_sn = QWidget(form_container)
            _h_sn = QHBoxLayout(_lw_sn)
            _h_sn.setContentsMargins(0, 0, 0, 0)
            _h_sn.setSpacing(4)
            _h_sn.addWidget(_lb_sn)
            apply_instructional_tooltip(
                "商品简称为唯一标识，编辑时不可修改",
                _lb_sn,
                self.edit_short_name,
                position=ToolTipPosition.TOP,
            )
            form_layout.addRow(_lw_sn, self.edit_short_name)
        else:
            form_layout.addRow(BodyLabel("商品简称：", form_container), self.edit_short_name)

        self.edit_short_title = LineEdit(form_container)
        self.edit_short_title.setPlaceholderText(
            f"可选，最多{CART_SHORT_TITLE_MAX_LEN}字；不填则预览用商品简称"
        )
        self.edit_short_title.setMaxLength(CART_SHORT_TITLE_MAX_LEN)
        self.edit_short_title.setClearButtonEnabled(True)
        form_layout.addRow(BodyLabel("商品短标题：", form_container), self.edit_short_title)

        # 抖音链接
        self.edit_douyin_link = LineEdit(form_container)
        self.edit_douyin_link.setPlaceholderText("请输入抖音购物车商品链接（可选）")
        self.edit_douyin_link.setClearButtonEnabled(True)
        form_layout.addRow(BodyLabel("抖音（链接）：", form_container), self.edit_douyin_link)

        # 快手商品名称
        self.edit_kuaishou_name = LineEdit(form_container)
        self.edit_kuaishou_name.setPlaceholderText("请输入快手商品名称（可选）")
        self.edit_kuaishou_name.setClearButtonEnabled(True)
        form_layout.addRow(BodyLabel("快手（商品名称）：", form_container), self.edit_kuaishou_name)

        # 视频号 ID 或链接
        self.edit_channels = LineEdit(form_container)
        self.edit_channels.setPlaceholderText("请输入视频号商品 ID 或链接（可选）")
        self.edit_channels.setClearButtonEnabled(True)
        form_layout.addRow(BodyLabel("视频号（ID或链接）：", form_container), self.edit_channels)

        # 小红书链接
        self.edit_xiaohongshu = LineEdit(form_container)
        self.edit_xiaohongshu.setPlaceholderText("请输入小红书商品链接（可选）")
        self.edit_xiaohongshu.setClearButtonEnabled(True)
        form_layout.addRow(BodyLabel("小红书（链接）：", form_container), self.edit_xiaohongshu)

        self.viewLayout.addWidget(form_container)

    def _fill_form(self, data: Dict[str, Any]):
        """将数据字典填入表单各字段。"""
        self.edit_short_name.setText(data.get("short_name") or "")
        self.edit_short_title.setText(data.get("short_title") or "")
        self.edit_douyin_link.setText(data.get("douyin_link") or "")
        self.edit_kuaishou_name.setText(data.get("kuaishou_product_name") or "")
        self.edit_channels.setText(data.get("channels_id_or_link") or "")
        self.edit_xiaohongshu.setText(data.get("xiaohongshu_link") or "")

    # ---------- 数据提取 ----------

    def get_form_data(self) -> Dict[str, Any]:
        """返回当前表单填写的数据字典。"""
        return {
            "short_name": self.edit_short_name.text().strip(),
            "short_title": self.edit_short_title.text().strip()[
                :CART_SHORT_TITLE_MAX_LEN
            ],
            "douyin_link": self.edit_douyin_link.text().strip(),
            "kuaishou_product_name": self.edit_kuaishou_name.text().strip(),
            "channels_id_or_link": self.edit_channels.text().strip(),
            "xiaohongshu_link": self.edit_xiaohongshu.text().strip(),
        }

    def validate(self) -> Optional[str]:
        """校验表单，返回错误提示文字；通过则返回 None。"""
        data = self.get_form_data()
        if not data["short_name"]:
            return "商品简称不能为空，请填写后再保存。"
        return None

    # ---------- 重写确认逻辑 ----------

    def accept(self):
        """点击"保存"时先校验，通过才关闭弹窗。"""
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
