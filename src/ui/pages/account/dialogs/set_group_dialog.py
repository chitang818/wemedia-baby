# -*- coding: utf-8 -*-
"""
设置账号组对话框
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem
)
from qfluentwidgets import (
    BodyLabel, ComboBox, PrimaryPushButton, PushButton
)

from src.ui.components.base_dialog import AppMessageBoxBase

class SetGroupDialog(AppMessageBoxBase):
    """设置账号组对话框"""
    
    def __init__(self, parent=None, current_group_id=None, groups=None):
        super().__init__(parent, header_title="设置账号组")
        
        self.groups = groups or []
        self.current_group_id = current_group_id
        self.selected_group_id = None
        
        self._init_ui()
        
    def _init_ui(self):
        """初始化UI"""
        # 下拉框选择分组
        self.group_combo = ComboBox(self)
        self.group_combo.setPlaceholderText("选择分分组")
        
        # 添加选项
        self.group_combo.addItem("未分类", userData=None)
        
        for group in self.groups:
            self.group_combo.addItem(group['group_name'], userData=group['id'])
            
        # 选中当前分组
        if self.current_group_id:
            for i in range(self.group_combo.count()):
                if self.group_combo.itemData(i) == self.current_group_id:
                    self.group_combo.setCurrentIndex(i)
                    break
        else:
            self.group_combo.setCurrentIndex(0)
            
        self.viewLayout.addWidget(self.group_combo)
        
        # 确定/取消按钮由 MessageBoxBase 提供，确定置于右侧
        self.yesButton.setText("确定")
        self.cancelButton.setText("取消")
        self.widget.setMinimumWidth(300)
        self._reorder_buttons()

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
            self.reject()
            return
        super().keyPressEvent(event)

    def validate(self):
        """验证并获取结果"""
        self.selected_group_id = self.group_combo.currentData()
        return True
