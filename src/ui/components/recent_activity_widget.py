"""
最近活动组件
文件路径：src/ui/components/recent_activity_widget.py
功能：工作台「最近活动」列表，展示最近发布记录（平台、账号、标题、状态、时间）
"""

from typing import List, Dict, Optional, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QCursor

from qfluentwidgets import (
    CardWidget, BodyLabel, CaptionLabel, SubtitleLabel,
    FluentIcon, IconWidget, isDarkTheme
)


STATUS_CONFIG = {
    "success": {"text": "成功", "light_color": "#107C10", "dark_color": "#6CCB5F"},
    "failed":  {"text": "失败", "light_color": "#E81123", "dark_color": "#FF6B6B"},
    "pending": {"text": "等待", "light_color": "#FFB900", "dark_color": "#FFD666"},
    "publishing": {"text": "发布中", "light_color": "#0078D4", "dark_color": "#4FC3F7"},
}


class ActivityItem(QWidget):
    """单条活动记录"""

    clicked = Signal(dict)

    def __init__(self, record: Dict[str, Any], platform_name: str, time_text: str, parent=None):
        super().__init__(parent)
        self._record = record
        self.setCursor(QCursor(Qt.PointingHandCursor))

        dark = isDarkTheme()
        hover_bg = "rgba(255,255,255,0.05)" if dark else "rgba(0,0,0,0.03)"
        self.setStyleSheet(
            f"ActivityItem {{ border-radius: 6px; }}"
            f"ActivityItem:hover {{ background: {hover_bg}; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        status = record.get("status", "pending")
        cfg = STATUS_CONFIG.get(status, STATUS_CONFIG["pending"])
        dot_color = cfg["dark_color"] if dark else cfg["light_color"]

        dot = QWidget(self)
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background: {dot_color}; border-radius: 4px;")
        layout.addWidget(dot, 0, Qt.AlignVCenter)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.setContentsMargins(0, 0, 0, 0)

        # 标题为空时不再显示「未命名内容」，改用「账号名」当主行、「平台」当副行；
        # 仍保持两行结构，避免与其他条目高度不一致。
        raw_title = (record.get("title") or "").strip()
        username = (record.get("platform_username") or "").strip() or "未知账号"
        if raw_title:
            main_text = raw_title
            sub_text = f"{platform_name}  ·  {username}"
        else:
            main_text = username
            sub_text = platform_name

        if len(main_text) > 28:
            main_text = main_text[:26] + "…"

        title_color = "#FFFFFF" if dark else "#1A1A1A"
        title_label = BodyLabel(main_text, self)
        title_label.setStyleSheet(f"color: {title_color}; font-size: 13px; font-weight: 500;")
        text_layout.addWidget(title_label)

        sub_color = "#AAAAAA" if dark else "#888888"
        sub_label = CaptionLabel(sub_text, self)
        sub_label.setStyleSheet(f"color: {sub_color}; font-size: 12px;")
        text_layout.addWidget(sub_label)

        layout.addLayout(text_layout, 1)

        right_layout = QVBoxLayout()
        right_layout.setSpacing(2)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        status_label = CaptionLabel(cfg["text"], self)
        status_label.setStyleSheet(f"color: {dot_color}; font-size: 12px; font-weight: 600;")
        status_label.setAlignment(Qt.AlignRight)
        right_layout.addWidget(status_label)

        time_label = CaptionLabel(time_text, self)
        time_color = "#888888" if dark else "#AAAAAA"
        time_label.setStyleSheet(f"color: {time_color}; font-size: 11px;")
        time_label.setAlignment(Qt.AlignRight)
        right_layout.addWidget(time_label)

        layout.addLayout(right_layout)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        self.clicked.emit(self._record)


class RecentActivityWidget(CardWidget):
    """最近活动列表组件"""

    record_clicked = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self._show_empty()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(0)

        header = QHBoxLayout()
        self.title_label = SubtitleLabel("最近发布", self)
        dark = isDarkTheme()
        title_color = "#FFFFFF" if dark else "#1A1A1A"
        self.title_label.setStyleSheet(f"font-weight: 600; font-size: 16px; color: {title_color};")
        header.addWidget(self.title_label)
        header.addStretch()
        layout.addLayout(header)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.list_container = QWidget(self)
        self.list_container.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 4, 0, 0)
        self.list_layout.setSpacing(2)
        self.scroll_area.setWidget(self.list_container)

        layout.addWidget(self.scroll_area, 1)

    def _show_empty(self):
        """显示空状态"""
        self._clear_items()
        dark = isDarkTheme()
        empty_color = "#888888" if dark else "#AAAAAA"
        empty_label = CaptionLabel("暂无发布记录", self.list_container)
        empty_label.setStyleSheet(f"color: {empty_color}; font-size: 13px; padding: 20px 0;")
        empty_label.setAlignment(Qt.AlignCenter)
        self.list_layout.addWidget(empty_label)
        self.list_layout.addStretch()

    def _clear_items(self):
        while self.list_layout.count():
            child = self.list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def set_records(self, records: List[Dict[str, Any]], platform_name_map: Dict[str, str] = None, format_time_fn=None):
        """设置活动记录列表

        Args:
            records: 发布记录字典列表（最近 N 条）
            platform_name_map: platform_id -> 中文名 映射
            format_time_fn: created_at 字符串 -> 显示文本 的格式化函数
        """
        self._clear_items()

        if not records:
            self._show_empty()
            return

        platform_name_map = platform_name_map or {}

        for record in records[:8]:
            platform_id = record.get("platform", "")
            platform_cn = platform_name_map.get(platform_id, platform_id)

            time_text = "刚刚"
            if format_time_fn:
                time_text = format_time_fn(record.get("created_at"))

            item = ActivityItem(record, platform_cn, time_text, self.list_container)
            item.clicked.connect(self.record_clicked.emit)
            self.list_layout.addWidget(item)

        self.list_layout.addStretch()
