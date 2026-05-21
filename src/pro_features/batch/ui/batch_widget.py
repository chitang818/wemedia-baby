"""
批量任务入口页面
文件路径：src/pro_features/batch/ui/batch_widget.py
功能：统计卡片、筛选区、任务执行列表（嵌入 BatchTaskExecutionWidget）。
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from qasync import asyncSlot

try:
    from qfluentwidgets import BodyLabel, CardWidget, ComboBox, LineEdit, PrimaryPushButton, SubtitleLabel

    FLUENT_WIDGETS_AVAILABLE = True
except ImportError:
    FLUENT_WIDGETS_AVAILABLE = False
    BodyLabel = QLabel
    CardWidget = QWidget
    ComboBox = QComboBox
    LineEdit = QLineEdit
    PrimaryPushButton = QPushButton
    SubtitleLabel = QLabel

from src.pro_features.batch.services.batch_task_manager_async import BatchTaskManagerAsync
from src.services.account.account_manager_async import AccountManagerAsync

from .create_task_dialog import CreateBatchTaskDialog
from .task_execution_widget import BatchTaskExecutionWidget

logger = logging.getLogger(__name__)


class BatchWidget(QWidget):
    """批量任务总览与入口。"""

    def __init__(
        self,
        user_id: int,
        batch_task_manager: BatchTaskManagerAsync,
        account_manager: AccountManagerAsync,
        parent=None,
    ):
        super().__init__(parent)
        self.user_id = user_id
        self.batch_task_manager = batch_task_manager
        self.account_manager = account_manager
        self._setup_ui()
        self._stats_refresh_timer = QTimer(self)
        self._stats_refresh_timer.setSingleShot(True)
        self._stats_refresh_timer.timeout.connect(self._update_statistics)
        self._schedule_statistics_refresh()

    def _schedule_statistics_refresh(self) -> None:
        self._stats_refresh_timer.start(0)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        header_layout = QHBoxLayout()
        if FLUENT_WIDGETS_AVAILABLE:
            title = SubtitleLabel("批量任务", self)
        else:
            title = QLabel("批量任务", self)
            title.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        btn_new_task = PrimaryPushButton("新建任务", self) if FLUENT_WIDGETS_AVAILABLE else QPushButton("新建任务", self)
        btn_new_task.clicked.connect(self._create_new_task)
        header_layout.addWidget(btn_new_task)
        layout.addLayout(header_layout)

        stats_layout = QHBoxLayout()
        self._create_stat_card(stats_layout, "任务总数", "0", "total_tasks")
        self._create_stat_card(stats_layout, "运行中", "0", "running_tasks")
        self._create_stat_card(stats_layout, "已完成", "0", "completed_tasks")
        self._create_stat_card(stats_layout, "失败", "0", "failed_tasks")
        layout.addLayout(stats_layout)

        filter_layout = QHBoxLayout()
        status_label = QLabel("状态筛选", self)
        self.status_filter = ComboBox(self) if FLUENT_WIDGETS_AVAILABLE else QComboBox(self)
        self.status_filter.addItems(["全部", "pending", "running", "paused", "completed", "failed", "cancelled"])
        self.status_filter.currentIndexChanged.connect(self._on_filter_changed)
        search_label = QLabel("搜索", self)
        self.search_edit = LineEdit(self) if FLUENT_WIDGETS_AVAILABLE else QLineEdit(self)
        self.search_edit.setPlaceholderText("按任务名称过滤…")
        self.search_edit.textChanged.connect(self._on_search_changed)
        filter_layout.addWidget(status_label)
        filter_layout.addWidget(self.status_filter)
        filter_layout.addStretch()
        filter_layout.addWidget(search_label)
        filter_layout.addWidget(self.search_edit)
        layout.addLayout(filter_layout)

        self.execution_widget = BatchTaskExecutionWidget(self.user_id, self.batch_task_manager, self)
        layout.addWidget(self.execution_widget)

    def _create_stat_card(self, layout: QHBoxLayout, title: str, value: str, key: str) -> None:
        if FLUENT_WIDGETS_AVAILABLE:
            card = CardWidget(self)
            card_layout = QVBoxLayout(card)
        else:
            card = QWidget(self)
            card.setStyleSheet("border: 1px solid #ddd; border-radius: 8px; padding: 10px;")
            card_layout = QVBoxLayout(card)
        title_label = BodyLabel(title, card) if FLUENT_WIDGETS_AVAILABLE else QLabel(title, card)
        value_label = SubtitleLabel(value, card) if FLUENT_WIDGETS_AVAILABLE else QLabel(value, card)
        value_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #0078d4;")
        card_layout.addWidget(title_label)
        card_layout.addWidget(value_label)
        layout.addWidget(card)
        setattr(self, f"stat_{key}", value_label)

    @asyncSlot()
    async def _update_statistics(self) -> None:
        try:
            tasks = await self.batch_task_manager.get_tasks(limit=500)
        except Exception as e:
            logger.debug("刷新批量任务统计失败: %s", e)
            return
        total = len(tasks)
        status_count: dict[str, int] = {}
        for t in tasks:
            s = str(t.get("status") or "unknown")
            status_count[s] = status_count.get(s, 0) + 1
        if hasattr(self, "stat_total_tasks"):
            self.stat_total_tasks.setText(str(total))
        if hasattr(self, "stat_running_tasks"):
            self.stat_running_tasks.setText(str(status_count.get("running", 0)))
        if hasattr(self, "stat_completed_tasks"):
            self.stat_completed_tasks.setText(str(status_count.get("completed", 0)))
        if hasattr(self, "stat_failed_tasks"):
            self.stat_failed_tasks.setText(str(status_count.get("failed", 0)))

    def _create_new_task(self) -> None:
        dialog = CreateBatchTaskDialog(
            self.user_id,
            self.account_manager,
            self.batch_task_manager,
            self.window() or self,
        )
        if dialog.exec():
            task_id = dialog.get_task_id()
            if task_id:
                logger.info("新建批量任务成功: id=%s", task_id)
                self._schedule_statistics_refresh()
                if hasattr(self.execution_widget, "_load_tasks"):
                    self.execution_widget._load_tasks()

    def _on_filter_changed(self, _index: int) -> None:
        if hasattr(self.execution_widget, "set_status_filter"):
            text = self.status_filter.currentText()
            self.execution_widget.set_status_filter(None if text == "全部" else text)

    def _on_search_changed(self, text: str) -> None:
        if hasattr(self.execution_widget, "set_search_text"):
            self.execution_widget.set_search_text(text.strip())
