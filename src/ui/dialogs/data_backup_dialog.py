from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt
from src.ui.components.base_dialog import AppMessageBoxBase
from qfluentwidgets import CheckBox

class DataBackupDialog(AppMessageBoxBase):
    """数据备份选项弹窗"""

    def __init__(self, parent=None):
        super().__init__(parent, header_title="选择备份内容")
        
        self.desc_label = QLabel("请勾选需要导出备份的数据模块：", self.widget)
        self.desc_label.setWordWrap(True)
        self.viewLayout.addWidget(self.desc_label)
        self.viewLayout.addSpacing(10)
        
        # 复选框选项
        self.cb_account = CheckBox("已登录自媒体账号、账号组与标签", self.widget)
        self.cb_account.setChecked(True)  # 默认选中
        self.viewLayout.addWidget(self.cb_account)
        self.viewLayout.addSpacing(5)

        self.cb_media = CheckBox("媒体库数据 (标准/随机文案库)", self.widget)
        self.cb_media.setChecked(True)
        self.viewLayout.addWidget(self.cb_media)
        self.viewLayout.addSpacing(5)

        self.cb_promotion = CheckBox("带货推广数据 (全功能)", self.widget)
        self.cb_promotion.setChecked(True)
        self.viewLayout.addWidget(self.cb_promotion)
        
        # 补充说明
        self.viewLayout.addSpacing(10)
        self.note_label = QLabel("注：导出账号数据时，将自动包含对应的浏览器环境配置（ZIP 打包可能需要较长时间，请耐心等待）。", self.widget)
        self.note_label.setWordWrap(True)
        self.note_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        self.viewLayout.addWidget(self.note_label)

        # 修改底部按钮文字
        self.yesButton.setText("确认导出")
        self.cancelButton.setText("取消")
        
        # 调整窗体大小
        self.widget.setMinimumWidth(380)
        
    def get_selected_modules(self) -> list[str]:
        """获取用户勾选的备份模块名称列表"""
        modules = []
        if self.cb_account.isChecked():
            modules.extend(["account_group", "account_tag", "platform_account"])
        if self.cb_media.isChecked():
            modules.extend(["copywriting", "random_copywriting_category", "random_copywriting_item"])
        if self.cb_promotion.isChecked():
            modules.extend(["cart_promotion", "location_promotion"])
        return modules
