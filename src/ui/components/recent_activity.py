"""
最近活动列表组件
文件路径：src/ui/components/recent_activity.py
功能：显示最近的活动列表（如发布记录、任务状态等）
"""

from typing import List, Dict, Any, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QScrollArea,
    QSizePolicy
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from qfluentwidgets import (
    CardWidget, IconWidget, FluentIconBase, BodyLabel, CaptionLabel,
    FluentIcon, SubtitleLabel
)

# 单条活动内边距与间距
ACTIVITY_ITEM_PADDING = 10
ACTIVITY_ITEM_SPACING = 12
ACTIVITY_ICON_SIZE = 36


class ActivityItemWidget(QWidget):
    """单条活动记录"""
    
    def __init__(self, title: str, subtitle: str, time_str: str, icon: FluentIconBase, status_color: str = "#666666", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(ACTIVITY_ITEM_PADDING, ACTIVITY_ITEM_PADDING, ACTIVITY_ITEM_PADDING, ACTIVITY_ITEM_PADDING)
        layout.setSpacing(ACTIVITY_ITEM_SPACING)
        
        # 1. 图标容器
        icon_container = QWidget(self)
        icon_container.setFixedSize(ACTIVITY_ICON_SIZE, ACTIVITY_ICON_SIZE)
        icon_container.setStyleSheet(f"background-color: {status_color}22; border-radius: {ACTIVITY_ICON_SIZE//2}px;")
        
        icon_layout = QVBoxLayout(icon_container)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        self.icon_widget = IconWidget(icon, icon_container)
        self.icon_widget.setFixedSize(18, 18)
        self.icon_widget.setStyleSheet(f"color: {status_color};")
        icon_layout.addWidget(self.icon_widget, 0, Qt.AlignCenter)
        layout.addWidget(icon_container)
        
        # 2. 标题 + 副标题
        content_layout = QVBoxLayout()
        content_layout.setSpacing(2)
        content_layout.setContentsMargins(0, 0, 0, 0)
        self.title_label = BodyLabel(title, self)
        self.title_label.setStyleSheet("font-weight: 500;")
        self.title_label.setWordWrap(True)
        self.subtitle_label = CaptionLabel(subtitle, self)
        self.subtitle_label.setStyleSheet("color: #757575;")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setMaximumWidth(280)
        content_layout.addWidget(self.title_label)
        content_layout.addWidget(self.subtitle_label)
        layout.addLayout(content_layout, 1)
        
        # 3. 时间（右侧）
        time_label = CaptionLabel(time_str, self)
        time_label.setStyleSheet("color: #999999;")
        layout.addWidget(time_label, 0, Qt.AlignRight | Qt.AlignVCenter)


class RecentActivityWidget(CardWidget):
    """最近活动列表组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(0)
        
        # 标题
        self.title_label = SubtitleLabel("最近活动", self)
        layout.addWidget(self.title_label)
        
        # 内容区：空状态与列表二选一展示
        self.content_stack = QWidget(self)
        content_stack_layout = QVBoxLayout(self.content_stack)
        content_stack_layout.setContentsMargins(0, 12, 0, 0)
        content_stack_layout.setSpacing(0)
        
        # 空状态：占满剩余空间并居中
        self.empty_container = QWidget(self)
        empty_layout = QVBoxLayout(self.empty_container)
        empty_layout.setContentsMargins(0, 0, 0, 0)
        empty_layout.addStretch(1)
        self.empty_label = CaptionLabel("暂无活动记录", self)
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("color: #999999; font-size: 13px;")
        empty_layout.addWidget(self.empty_label, 0, Qt.AlignCenter)
        empty_layout.addStretch(1)
        content_stack_layout.addWidget(self.empty_container, 1)
        
        # 列表区（带滚动）
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.scroll_area.setVisible(False)
        
        self.list_container = QWidget(self)
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(6)
        self.scroll_area.setWidget(self.list_container)
        content_stack_layout.addWidget(self.scroll_area, 1)
        
        layout.addWidget(self.content_stack, 1)
        
    def set_activities(self, activities: List[Dict[str, Any]]):
        """设置活动数据
        
        Args:
            activities: 列表，每项包含:
                 - title: 标题
                 - subtitle: 副标题
                 - time: 时间
                 - icon: FluentIcon枚举 (可选)
                 - status: 'success' | 'failed' | 'info' (决定颜色)
        """
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        if not activities:
            self.empty_container.setVisible(True)
            self.scroll_area.setVisible(False)
            return
            
        self.empty_container.setVisible(False)
        self.scroll_area.setVisible(True)
        
        for activity in activities:
            status = activity.get('status', 'info')
            if status == 'success':
                color = "#107C10"
                icon = activity.get('icon', FluentIcon.ACCEPT)
            elif status == 'failed':
                color = "#E81123"
                icon = activity.get('icon', FluentIcon.CANCEL)
            else:
                color = "#0078D4"
                icon = activity.get('icon', FluentIcon.INFO)
            
            item = ActivityItemWidget(
                title=activity.get('title', '未知活动'),
                subtitle=activity.get('subtitle', ''),
                time_str=activity.get('time', ''),
                icon=icon,
                status_color=color,
                parent=self.list_container
            )
            self.list_layout.addWidget(item)
        
        self.list_layout.addStretch()
