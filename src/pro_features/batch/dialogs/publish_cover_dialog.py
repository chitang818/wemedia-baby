"""
封面设置弹窗
文件路径：src/pro_features/batch/dialogs/publish_cover_dialog.py
功能：提取自批量视频发布页面的封面配置功能，用于在弹窗中配置封面（首帧或本地）
"""
import os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QButtonGroup, QFileDialog
from qfluentwidgets import (
    RadioButton, PushButton, FluentIcon, BodyLabel
)

from src.ui.components.base_dialog import AppMessageBoxBase

class PublishCoverDialog(AppMessageBoxBase):
    """
    发布封面设置弹窗
    """
    def __init__(self, initial_cover_type="first_frame", initial_cover_path="", parent=None):
        super().__init__(parent, header_title="设置视频封面")
        self.cover_type = initial_cover_type
        self.cover_path = initial_cover_path

        self.widget.setMinimumWidth(400)
        self.yesButton.setText("确定")
        self.cancelButton.setText("取消")
        self._reorder_buttons()

        row = QHBoxLayout()
        row.setSpacing(12)
        self.radio_first_frame = RadioButton("首帧封面", self)
        self.radio_local_cover = RadioButton("本地封面", self)
        
        self.cover_btn_group = QButtonGroup(self)
        self.cover_btn_group.addButton(self.radio_first_frame)
        self.cover_btn_group.addButton(self.radio_local_cover)
        
        row.addWidget(self.radio_first_frame)
        row.addWidget(self.radio_local_cover)
        row.addStretch()
        self.viewLayout.addLayout(row)

        # 本地文件选择行
        cover_file_row = QHBoxLayout()
        cover_file_row.setSpacing(8)
        self.btn_browse_cover = PushButton(FluentIcon.PHOTO, "选择封面图", self)
        self.btn_browse_cover.setFixedSize(100, 24)
        self.btn_browse_cover.clicked.connect(self._on_browse_cover)
        self.cover_path_label = BodyLabel("未选择封面", self)
        cover_file_row.addWidget(self.btn_browse_cover)
        cover_file_row.addWidget(self.cover_path_label, 1)
        self.viewLayout.addLayout(cover_file_row)

        # 绑定显隐逻辑
        self.btn_browse_cover.setVisible(False)
        self.cover_path_label.setVisible(False)
        self.radio_local_cover.toggled.connect(self.btn_browse_cover.setVisible)
        self.radio_local_cover.toggled.connect(self.cover_path_label.setVisible)

        # 恢复初始状态
        if self.cover_type == "custom":
            self.radio_local_cover.setChecked(True)
            if self.cover_path:
                self.cover_path_label.setText(os.path.basename(self.cover_path))
        else:
            self.radio_first_frame.setChecked(True)

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

    def _on_browse_cover(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择封面图片", "",
            "图片文件 (*.jpg *.jpeg *.png *.bmp *.webp);;所有文件 (*.*)",
        )
        if path:
            self.cover_path = path
            self.cover_path_label.setText(os.path.basename(path))

    def get_cover_settings(self):
        """返回当前的配置 (cover_type, cover_path)"""
        if self.radio_local_cover.isChecked():
            return "custom", self.cover_path
        else:
            return "first_frame", ""
