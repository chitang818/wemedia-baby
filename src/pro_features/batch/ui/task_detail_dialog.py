"""
批量任务详情对话框
文件路径：src/pro_features/batch/ui/task_detail_dialog.py
功能：异步加载任务并展示基本信息与 script_config（JSON）。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout

from qasync import asyncSlot

from src.ui.components.base_dialog import install_escape_reject_shortcut, resolve_top_level_window_parent

try:
    from qfluentwidgets import PlainTextEdit, PushButton

    FLUENT_WIDGETS_AVAILABLE = True
except ImportError:
    FLUENT_WIDGETS_AVAILABLE = False
    PlainTextEdit = QPlainTextEdit
    PushButton = QPushButton

logger = logging.getLogger(__name__)


class TaskDetailDialog(QDialog):
    """展示单条批量任务详情（只读）。"""

    def __init__(self, task_id: int, batch_task_manager: Any, parent=None):
        super().__init__(resolve_top_level_window_parent(parent))
        install_escape_reject_shortcut(self)
        self._task_id = int(task_id)
        self._manager = batch_task_manager
        self.setWindowTitle(f"任务详情 — {self._task_id}")
        self.resize(720, 560)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("任务信息（只读）", self))
        self._text = PlainTextEdit(self)
        self._text.setReadOnly(True)
        layout.addWidget(self._text)

        row = QHBoxLayout()
        row.addStretch()
        btn = PushButton("关闭", self) if FLUENT_WIDGETS_AVAILABLE else QPushButton("关闭", self)
        btn.clicked.connect(self.accept)
        row.addWidget(btn)
        layout.addLayout(row)

        QTimer.singleShot(0, self._load_details_async)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    @asyncSlot()
    async def _load_details_async(self) -> None:
        try:
            task = await self._manager.get_task_by_id(self._task_id)
        except Exception as e:
            logger.exception("加载任务详情失败: %s", e)
            self._text.setPlainText(f"加载失败：{e}")
            return

        if not task:
            self._text.setPlainText("未找到该任务（可能已删除）。")
            return

        sc_raw = task.get("script_config")
        if isinstance(sc_raw, str):
            try:
                sc_pretty = json.dumps(json.loads(sc_raw), ensure_ascii=False, indent=2)
            except Exception:
                sc_pretty = sc_raw
        else:
            try:
                sc_pretty = json.dumps(sc_raw or {}, ensure_ascii=False, indent=2)
            except Exception:
                sc_pretty = str(sc_raw)

        lines = [
            f"任务ID: {task.get('id')}",
            f"任务名称: {task.get('task_name', '')}",
            f"平台账号: {task.get('platform_username', '')}",
            f"平台: {task.get('platform', '')}",
            f"类型: {task.get('task_type', '')}",
            f"状态: {task.get('status', '')}",
            f"视频数: {task.get('video_count', 0)}",
            f"已完成: {task.get('completed_count', 0)}",
            f"失败数: {task.get('failed_count', 0)}",
            f"重试次数: {task.get('retry_count', '')}",
            f"间隔(秒): {task.get('delay_seconds', '')}",
            f"创建时间: {task.get('created_at', '')}",
            "",
            "—— script_config ——",
            sc_pretty,
        ]
        self._text.setPlainText("\n".join(lines))
