"""
发布记录详情对话框
文件路径：src/ui/dialogs/publish_record_detail_dialog.py
功能：显示发布记录详细信息
"""

from typing import Dict, Any, Optional
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QWidget
from PySide6.QtCore import Qt
import logging
import json

try:
    from qfluentwidgets import BodyLabel, SubtitleLabel, ScrollArea
    from src.ui.components.base_dialog import AppMessageBoxBase
    FLUENT_WIDGETS_AVAILABLE = True
except ImportError:
    FLUENT_WIDGETS_AVAILABLE = False
    AppMessageBoxBase = QDialog  # type: ignore[misc, assignment]

from src.ui.components.base_dialog import install_escape_reject_shortcut, resolve_top_level_window_parent

logger = logging.getLogger(__name__)


class PublishRecordDetailDialog(AppMessageBoxBase if FLUENT_WIDGETS_AVAILABLE else QDialog):
    """发布记录详情对话框"""
    
    def __init__(self, record: Dict[str, Any], parent: Optional[QDialog] = None):
        """初始化发布记录详情对话框
        
        Args:
            record: 发布记录字典
            parent: 父对话框
        """
        if FLUENT_WIDGETS_AVAILABLE:
            super().__init__(parent, header_title="发布记录详情")
        else:
            super().__init__(resolve_top_level_window_parent(parent))
            install_escape_reject_shortcut(self)
        if not FLUENT_WIDGETS_AVAILABLE:
            self.setWindowTitle("发布记录详情")
            self.setModal(True)
        
        self.record = record
        self._setup_ui()
    
    def _setup_ui(self):
        """设置UI"""
        if not FLUENT_WIDGETS_AVAILABLE:
            layout = QVBoxLayout(self)
            layout.setSpacing(12)
            title = QLabel("发布记录详情", self)
            title.setStyleSheet("font-weight: bold;")
            layout.addWidget(title)
            edit = QTextEdit(self)
            edit.setReadOnly(True)
            try:
                edit.setPlainText(json.dumps(self.record, ensure_ascii=False, indent=2))
            except Exception:
                edit.setPlainText(str(self.record))
            layout.addWidget(edit, stretch=1)
            return

        # MessageBoxBase 提供 self.widget / self.viewLayout
        self.widget.setMinimumWidth(520)
        self.yesButton.setText("关闭")
        self.cancelButton.hide()
        try:
            self.yesButton.clicked.disconnect()
        except Exception:
            pass
        self.yesButton.clicked.connect(self.accept)

        self.viewLayout.addSpacing(8)
        
        # 创建滚动区域
        scroll_area = ScrollArea(self.widget)
        scroll_content = QWidget(self.widget)
        scroll_content.setStyleSheet("background: transparent;")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(12)
        
        # 基本信息
        self._add_section(scroll_layout, scroll_content, "基本信息", [
            ("记录ID", str(self.record.get('id', ''))),
            ("平台", self._get_platform_display(self.record.get('platform', ''))),
            ("账号组", (self.record.get("account_group_name") or "").strip() or "—"),
            ("账号", self.record.get('account_name', '') or self.record.get('platform_username', '')),
            ("文件类型", self.record.get('file_type', '')),
            ("状态", self._get_status_display(self.record.get('status', ''))),
            ("创建时间", self.record.get('created_at', '')),
            ("更新时间", self.record.get('updated_at', '') or '未更新'),
        ])
        
        # 文件信息
        _raw_fp = self.record.get('file_path', '') or ''
        _fp_parts = [p.strip() for p in _raw_fp.split(",") if p.strip()]
        if _fp_parts and all(p == "__DELETED__" for p in _fp_parts):
            _fp_display = "已删除"
        else:
            _fp_display = _raw_fp
        self._add_section(scroll_layout, scroll_content, "文件信息", [
            ("文件路径", _fp_display),
        ])
        
        # 发布内容
        self._add_section(scroll_layout, scroll_content, "发布内容", [
            ("标题", self.record.get('title', '') or '(无标题)'),
            ("描述", self.record.get('description', '') or '(无描述)'),
            ("标签", self._format_tags(self.record.get('tags'))),
        ])
        
        # 发布结果
        result_items = []
        if self.record.get('publish_url'):
            result_items.append(("发布链接", self.record.get('publish_url')))
        if self.record.get('error_message'):
            result_items.append(("错误信息", self.record.get('error_message')))
        if self.record.get('diagnostic_path'):
            result_items.append(("诊断目录", self.record.get('diagnostic_path')))
        
        if result_items:
            self._add_section(scroll_layout, scroll_content, "发布结果", result_items)
        
        scroll_area.setWidget(scroll_content)
        scroll_area.setWidgetResizable(True)
        self.viewLayout.addWidget(scroll_area)
    
    def _add_section(self, layout: QVBoxLayout, parent, title: str, items: list):
        """添加信息区块"""
        section_title = SubtitleLabel(title, parent)
        layout.addWidget(section_title)
        
        for label, value in items:
            item_layout = QHBoxLayout()
            
            label_widget = BodyLabel(f"{label}:", parent)
            label_widget.setMinimumWidth(100)
            item_layout.addWidget(label_widget)
            
            value_widget = BodyLabel(str(value), parent)
            value_widget.setWordWrap(True)
            value_widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
            item_layout.addWidget(value_widget, stretch=1)
            
            layout.addLayout(item_layout)
        
        layout.addSpacing(8)
    
    @staticmethod
    def _get_platform_display(platform: str) -> str:
        """获取平台显示名称"""
        from src.utils.platform_names import get_platform_display_name
        return get_platform_display_name(platform)
    
    def _get_status_display(self, status: str) -> str:
        """获取状态显示名称"""
        status_map = {
            'success': '✅ 成功',
            'failed': '❌ 失败',
            'pending': '⏳ 待发布'
        }
        return status_map.get(status, status)
    
    def _format_tags(self, tags_str: Optional[str]) -> str:
        """格式化标签"""
        if not tags_str:
            return '(无标签)'
        
        try:
            if isinstance(tags_str, str):
                tags = json.loads(tags_str)
            else:
                tags = tags_str
            
            if isinstance(tags, list):
                return ', '.join(tags) if tags else '(无标签)'
            else:
                return str(tags)
        except (TypeError, ValueError):
            return tags_str or '(无标签)'

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

