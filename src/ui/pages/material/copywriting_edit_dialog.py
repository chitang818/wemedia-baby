"""
文案新建/编辑弹窗
文件路径：src/ui/pages/material/copywriting_edit_dialog.py
功能：提供统一的文案表单弹窗，支持新建和编辑两种模式，包含作品编号、作品标题、作品描述、文案内容四个字段。
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any

from PySide6.QtWidgets import QWidget, QVBoxLayout, QFormLayout
from PySide6.QtCore import Qt

from qfluentwidgets import (
    LineEdit,
    PlainTextEdit,
    BodyLabel,
)

from src.ui.components.base_dialog import StandardBaseDialog
from src.infrastructure.common.copywriting_work_id import (
    COPYWRITING_WORK_ID_FORMAT_HINT,
    is_valid_copywriting_work_id,
)

logger = logging.getLogger(__name__)


class CopywritingEditDialog(StandardBaseDialog):
    """文案新建/编辑弹窗。

    Args:
        parent: 父控件。
        item_data: 传入现有文案字典时进入编辑模式；传入 None 时进入新建模式。
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        item_data: Optional[Dict[str, Any]] = None,
        strict_work_id: bool = True,
    ):
        is_edit = item_data is not None
        title = "编辑文案" if is_edit else "新建文案"
        super().__init__(parent, title)

        self._accepting = False
        self._is_edit = is_edit
        self._item_data = item_data or {}
        self._strict_work_id = strict_work_id

        # 弹窗最小宽度稍大，方便填写文案内容
        self.widget.setMinimumWidth(520)

        self._build_form()

        # 编辑模式下将现有数据填入表单
        if is_edit:
            self._fill_form(self._item_data)

        # 确定按钮文字
        self.set_yes_button_text("保存")
        # 加固：确保点“保存”一定会触发 accept（有些情况下 MessageBoxBase 默认连接可能被覆盖）
        try:
            self.yesButton.clicked.connect(self.accept)
        except Exception:
            # 不影响主要流程
            pass

    # ---------- 表单构建 ----------

    def _build_form(self):
        """构建四字段表单。"""
        form_container = QWidget(self.widget)
        form_layout = QFormLayout(form_container)
        form_layout.setContentsMargins(0, 8, 0, 8)
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # 作品编号
        self.edit_work_id = LineEdit(form_container)
        placeholder = COPYWRITING_WORK_ID_FORMAT_HINT if self._strict_work_id else "作品编号（可选）"
        self.edit_work_id.setPlaceholderText(placeholder)
        if self._strict_work_id:
            self.edit_work_id.setMaxLength(5)
        self.edit_work_id.setClearButtonEnabled(True)
        form_layout.addRow(BodyLabel("作品编号：", form_container), self.edit_work_id)
        if self._strict_work_id:
            self._work_id_hint = BodyLabel(
                f"格式说明：{COPYWRITING_WORK_ID_FORMAT_HINT}。",
                form_container,
            )
            self._work_id_hint.setStyleSheet("color: #888; font-size: 11px;")
            self._work_id_hint.setWordWrap(True)
            form_layout.addRow("", self._work_id_hint)

        # 作品标题
        self.edit_short_title = LineEdit(form_container)
        self.edit_short_title.setPlaceholderText("请输入作品标题（发布时的标题）")
        self.edit_short_title.setClearButtonEnabled(True)
        form_layout.addRow(BodyLabel("作品标题：", form_container), self.edit_short_title)

        # 作品描述
        self.edit_description = LineEdit(form_container)
        self.edit_description.setPlaceholderText("请输入作品描述（可选）")
        self.edit_description.setClearButtonEnabled(True)
        form_layout.addRow(BodyLabel("作品描述：", form_container), self.edit_description)

        # 文案内容（多行）
        self.edit_content = PlainTextEdit(form_container)
        self.edit_content.setPlaceholderText("请输入文案内容（可多行）")
        self.edit_content.setFixedHeight(120)
        form_layout.addRow(BodyLabel("文案内容：", form_container), self.edit_content)

        self.viewLayout.addWidget(form_container)

    def _fill_form(self, data: Dict[str, Any]):
        """将数据字典填入表单各字段。"""
        self.edit_work_id.setText(data.get("work_id") or "")
        self.edit_short_title.setText(data.get("short_title") or "")
        self.edit_description.setText(data.get("description") or "")
        self.edit_content.setPlainText(data.get("content") or "")

    # ---------- 数据提取 ----------

    def get_form_data(self) -> Dict[str, Any]:
        """返回当前表单填写的数据字典。"""
        return {
            "work_id": self.edit_work_id.text().strip(),
            "short_title": self.edit_short_title.text().strip(),
            "description": self.edit_description.text().strip(),
            "content": self.edit_content.toPlainText().strip(),
        }

    def validate(self) -> Optional[str]:
        """校验表单，返回错误提示文字；通过则返回 None。"""
        data = self.get_form_data()
        wid = data["work_id"]
        
        # 严格模式校验
        if self._strict_work_id:
            if not wid:
                return "作品编号不能为空，请填写后再保存。"
            if not is_valid_copywriting_work_id(wid):
                return f"作品编号格式不正确：{COPYWRITING_WORK_ID_FORMAT_HINT}。"
        else:
            # 非严格模式（随机库）：内容不能为空即可
            if not data.get("content"):
                return "文案内容不能为空。"
                
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
