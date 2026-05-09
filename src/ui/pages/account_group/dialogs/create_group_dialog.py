"""
创建/编辑账号组弹窗
文件路径：src/ui/pages/account_group/dialogs/create_group_dialog.py
"""

from typing import Optional, Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout
from qfluentwidgets import LineEdit, TextEdit

from src.ui.components.base_dialog import AppMessageBoxBase


class CreateGroupDialog(AppMessageBoxBase):
    """创建/编辑账号组弹窗"""
    
    def __init__(self, parent=None, group_data: Optional[Dict] = None):
        """初始化弹窗
        
        Args:
            parent: 父窗口
            group_data: 编辑时传入的账号组数据，为 None 时表示新建
        """
        self.group_data = group_data
        self.is_edit_mode = group_data is not None
        title_text = "编辑账号组" if self.is_edit_mode else "新建账号组"
        super().__init__(parent, header_title=title_text)
        
        self._setup_ui()
        self._load_data()
    
    def _setup_ui(self):
        """设置UI"""
        # 账号组名称
        self.name_edit = LineEdit(self)
        self.name_edit.setPlaceholderText("请输入账号组名称")
        self.name_edit.setClearButtonEnabled(True)
        self.viewLayout.addWidget(self.name_edit)
        
        # 描述（可选）
        self.desc_edit = TextEdit(self)
        self.desc_edit.setPlaceholderText("请输入描述（可选）")
        self.desc_edit.setMaximumHeight(80)
        self.viewLayout.addWidget(self.desc_edit)
        
        # 设置弹窗大小
        self.widget.setMinimumWidth(350)
        
        # 设置按钮文字，确定置于右侧
        self.yesButton.setText("确定")
        self.cancelButton.setText("取消")
        self._reorder_buttons()

        # 验证输入
        self.name_edit.textChanged.connect(self._validate)
        self._validate()
    
    def _load_data(self):
        """加载编辑数据"""
        if self.group_data:
            self.name_edit.setText(self.group_data.get('group_name', ''))
            self.desc_edit.setPlainText(self.group_data.get('description', ''))
    
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

    def _validate(self):
        """验证输入"""
        is_valid = bool(self.name_edit.text().strip())
        self.yesButton.setEnabled(is_valid)
    
    def get_group_name(self) -> str:
        """获取账号组名称"""
        return self.name_edit.text().strip()
    
    def get_description(self) -> str:
        """获取描述"""
        return self.desc_edit.toPlainText().strip()
