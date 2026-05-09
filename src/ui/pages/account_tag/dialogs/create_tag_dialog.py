"""
创建/编辑账号标签对话框
"""

from typing import Dict, Optional, Any
from PySide6.QtWidgets import QVBoxLayout, QWidget, QHBoxLayout
from PySide6.QtCore import Qt
from qfluentwidgets import LineEdit, MessageBoxBase, SubtitleLabel, ComboBox, BodyLabel

class CreateTagDialog(MessageBoxBase):
    """创建或编辑账号标签对话框"""

    def __init__(self, parent=None, tag_data: Optional[Dict[str, Any]] = None):
        super().__init__(parent)
        self.tag_data = tag_data
        self.is_edit = tag_data is not None
        
        self.titleLabel = SubtitleLabel(
            "编辑账号标签" if self.is_edit else "新建账号标签", self
        )

        # 标签类型（账号标签 / 账号组标签）
        self.type_combo = ComboBox(self)
        self.type_combo.addItems(["账号标签", "账号组标签"])

        init_type = (self.tag_data or {}).get("tag_type") if self.tag_data else None
        if not init_type:
            try:
                has_groups = bool((self.tag_data or {}).get("groups"))
                has_accounts = bool((self.tag_data or {}).get("accounts"))
                if has_groups and not has_accounts:
                    init_type = "group"
                else:
                    init_type = "account"
            except Exception:
                init_type = "account"

        self.type_combo.setCurrentIndex(0 if init_type == "account" else 1)
        # 编辑时不允许改类型，避免与已关联对象冲突
        if self.is_edit:
            self.type_combo.setEnabled(False)
        
        self.name_edit = LineEdit(self)
        self.name_edit.setPlaceholderText("请输入标签名称，如“农业”")
        self.name_edit.setClearButtonEnabled(True)
        
        if self.is_edit and self.tag_data:
            self.name_edit.setText(self.tag_data.get('name', ''))

        # 将组件添加到布局
        self.viewLayout.addWidget(self.titleLabel)

        type_row = QWidget(self)
        type_lay = QHBoxLayout(type_row)
        type_lay.setContentsMargins(0, 0, 0, 0)
        type_lay.setSpacing(10)
        type_lay.addWidget(BodyLabel("标签类型", type_row))
        type_lay.addWidget(self.type_combo, 1)
        self.viewLayout.addWidget(type_row)

        self.viewLayout.addWidget(self.name_edit)
        
        # 设置最小宽度
        self.widget.setMinimumWidth(350)
        
        # 连接信号
        self.name_edit.textChanged.connect(self._validate)
        
        self.yesButton.setText("保存")
        self.cancelButton.setText("取消")
        
        # 初始验证
        self._validate()

    def _validate(self):
        """验证输入"""
        name = self.name_edit.text().strip()
        self.yesButton.setEnabled(bool(name))

    def get_tag_name(self) -> str:
        """获取输入的标签名称"""
        return self.name_edit.text().strip()

    def get_tag_type(self) -> str:
        """获取标签类型：account / group"""
        try:
            return "group" if self.type_combo.currentIndex() == 1 else "account"
        except Exception:
            return "account"
