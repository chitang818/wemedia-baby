"""
通用占位页面
文件路径：src/ui/pages/common/placeholder_page.py
功能：用于显示"功能开发中"的通用页面
"""

from typing import Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Qt

try:
    from qfluentwidgets import (
        CardWidget, SubtitleLabel, BodyLabel, IconWidget, FluentIcon
    )
    FLUENT_WIDGETS_AVAILABLE = True
except ImportError:
    FLUENT_WIDGETS_AVAILABLE = False

from ..base_page import BasePage

class PlaceholderPage(BasePage):
    """通用占位页面"""
    
    def __init__(self, title: str, description: str = "该功能正在疯狂开发中，敬请期待...", icon=None, parent: Optional[QWidget] = None):
        """初始化
        
        Args:
            title: 页面标题
            description: 描述文本
            icon: 图标 (FluentIcon)
            parent: 父组件
        """
        super().__init__(title, parent)
        self.description = description
        self.icon = icon
        self._setup_content()
        
    def _setup_content(self):
        """设置内容"""
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(40, 60, 40, 60)
        layout.setSpacing(20)
        
        if FLUENT_WIDGETS_AVAILABLE and self.icon:
            icon_widget = IconWidget(self.icon, card)
            icon_widget.setFixedSize(64, 64)
            layout.addWidget(icon_widget, 0, Qt.AlignCenter)
            
        title_label = SubtitleLabel(self.title, card)
        desc_label = BodyLabel(self.description, card)
        
        title_label.setAlignment(Qt.AlignCenter)
        desc_label.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(title_label, 0, Qt.AlignCenter)
        layout.addWidget(desc_label, 0, Qt.AlignCenter)
        
        self.content_layout.addWidget(card)
