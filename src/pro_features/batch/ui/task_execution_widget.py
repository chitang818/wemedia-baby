"""
批量任务执行列表
文件路径：src/pro_features/batch/ui/task_execution_widget.py
功能：展示任务表、进度与日志；启动执行线程、打开任务详情。
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:
    from qfluentwidgets import CardWidget, PlainTextEdit, PrimaryPushButton, ProgressBar, PushButton, TableWidget

    FLUENT_WIDGETS_AVAILABLE = True
except ImportError:
    FLUENT_WIDGETS_AVAILABLE = False
    TableWidget = QTableWidget
    PushButton = QPushButton
    PrimaryPushButton = QPushButton
    ProgressBar = QProgressBar
    PlainTextEdit = QTextEdit
    CardWidget = QWidget

from src.pro_features.batch.services.batch_task_executor import BatchTaskExecutor, BatchTaskProgressEvent
from src.pro_features.batch.services.batch_task_manager_async import BatchTaskManagerAsync
from src.ui.pages.publish.task_field_display import TASK_FIELD_EMPTY_DISPLAY, task_field_str_or_dash
from src.ui.utils.async_helper import AsyncWorker

from .task_detail_dialog import TaskDetailDialog

logger = logging.getLogger(__name__)


class BatchTaskExecutionWidget(QWidget):
    """批量任务列表与执行控制。"""

    def __init__(self, user_id: int, batch_task_manager: Any, parent=None):
        super().__init__(parent)
        self.user_id = user_id
        self.batch_task_manager = batch_task_manager
        self._is_async = isinstance(batch_task_manager, BatchTaskManagerAsync)
        self.task_executor = BatchTaskExecutor(batch_task_manager)
        self.running_threads: Dict[int, threading.Thread] = {}
        self._active_workers: List[AsyncWorker] = []
        self._status_filter: Optional[str] = None
        self._search_text: str = ""

        self._setup_ui()
        self._setup_connections()
        self._load_tasks()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._load_tasks)
        self.refresh_timer.start(8000)

    def set_status_filter(self, status: Optional[str]) -> None:
        self._status_filter = status
        self._load_tasks()

    def set_search_text(self, text: str) -> None:
        self._search_text = (text or "").strip().lower()
        self._load_tasks()

    def stop_all_tasks(self) -> None:
        if hasattr(self, "refresh_timer") and self.refresh_timer.isActive():
            self.refresh_timer.stop()
        for tid in list(self.running_threads.keys()):
            try:
                self.task_executor.cancel_task(tid)
            except Exception:
                pass
        self.running_threads.clear()
        if hasattr(self.task_executor, "shutdown"):
            self.task_executor.shutdown()

    def closeEvent(self, event):
        self.stop_all_tasks()
        super().closeEvent(event)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("任务列表", self)
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()
        btn_refresh = PushButton("刷新", self) if FLUENT_WIDGETS_AVAILABLE else PushButton("刷新", self)
        btn_refresh.clicked.connect(self._load_tasks)
        header.addWidget(btn_refresh)
        layout.addLayout(header)

        self.task_table = TableWidget(self) if FLUENT_WIDGETS_AVAILABLE else QTableWidget(self)
        self.task_table.setColumnCount(7)
        self.task_table.setHorizontalHeaderLabels(
            ["ID", "任务名", "账号", "平台", "状态", "进度", "操作"]
        )
        _th = self.task_table.horizontalHeader()
        _th.setStretchLastSection(True)
        _th.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        self.task_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.task_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.task_table)

        if FLUENT_WIDGETS_AVAILABLE:
            detail_card = CardWidget(self)
            detail_layout = QVBoxLayout(detail_card)
        else:
            detail_card = QWidget(self)
            detail_layout = QVBoxLayout(detail_card)
        detail_layout.setSpacing(6)
        detail_layout.addWidget(QLabel("当前进度", self))
        self.progress_bar = ProgressBar(self) if FLUENT_WIDGETS_AVAILABLE else QProgressBar(self)
        self.progress_bar.setVisible(False)
        detail_layout.addWidget(self.progress_bar)
        detail_layout.addWidget(QLabel("日志", self))
        self.log_text = PlainTextEdit(self) if FLUENT_WIDGETS_AVAILABLE else QTextEdit(self)
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(200)
        detail_layout.addWidget(self.log_text)
        layout.addWidget(detail_card)

    def _setup_connections(self) -> None:
        self.task_executor.progress_updated.connect(self._on_progress_updated)
        self.task_executor.task_completed.connect(self._on_task_completed)
        self.task_executor.task_failed.connect(self._on_task_failed)

    def _load_tasks(self) -> None:
        if not self._is_async:
            return

        async def load_tasks_async():
            if self._status_filter:
                return await self.batch_task_manager.get_tasks(status=self._status_filter, limit=200)
            return await self.batch_task_manager.get_tasks(limit=200)

        worker = AsyncWorker(load_tasks_async)
        worker.finished.connect(self._on_tasks_loaded)
        worker.error.connect(self._on_load_tasks_error)
        worker.setParent(self)
        self._active_workers.append(worker)
        worker.start()

    def _on_tasks_loaded(self, tasks: object) -> None:
        try:
            if not isinstance(tasks, list):
                tasks = []
            if self._search_text:
                tasks = [
                    t
                    for t in tasks
                    if self._search_text in str(t.get("task_name", "")).lower()
                ]
            self._update_task_table(tasks)
        except Exception as e:
            logger.error("更新任务表失败: %s", e, exc_info=True)

    def _on_load_tasks_error(self, error: str) -> None:
        logger.warning("加载任务列表失败: %s", error)
        self.task_table.setRowCount(0)

    def _update_task_table(self, tasks: List[Dict[str, Any]]) -> None:
        self.task_table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            tid = task.get("id")
            name = task_field_str_or_dash(task.get("task_name", ""))
            account = task_field_str_or_dash(
                task.get("platform_username") or task.get("account_name", "")
            )
            platform = task_field_str_or_dash(task.get("platform", ""))
            status = task_field_str_or_dash(task.get("status", "pending"))
            completed = int(task.get("completed_count") or 0)
            total = int(task.get("video_count") or 0)
            failed = int(task.get("failed_count") or 0)

            _ac = Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
            for col, text in enumerate(
                (
                    str(tid),
                    name,
                    account,
                    platform,
                    status,
                    f"{completed}/{total}（失败 {failed}）" if total else TASK_FIELD_EMPTY_DISPLAY,
                )
            ):
                it = QTableWidgetItem(text)
                it.setTextAlignment(_ac)
                self.task_table.setItem(row, col, it)

            btn_widget = QWidget()
            bl = QHBoxLayout(btn_widget)
            bl.setContentsMargins(4, 2, 4, 2)
            bl.setSpacing(6)

            if status in ("pending", "paused", "failed"):
                btn_start = PrimaryPushButton("开始", btn_widget) if FLUENT_WIDGETS_AVAILABLE else PushButton("开始", btn_widget)
                btn_start.clicked.connect(lambda _=False, i=tid: self._start_task(int(i)))
                bl.addWidget(btn_start)
            if status == "running":
                btn_cancel = PushButton("停止", btn_widget) if FLUENT_WIDGETS_AVAILABLE else PushButton("停止", btn_widget)
                btn_cancel.clicked.connect(lambda _=False, i=tid: self._cancel_task(int(i)))
                bl.addWidget(btn_cancel)

            btn_detail = PushButton("详情", btn_widget) if FLUENT_WIDGETS_AVAILABLE else PushButton("详情", btn_widget)
            btn_detail.clicked.connect(lambda _=False, i=tid: self._show_task_detail(int(i)))
            bl.addWidget(btn_detail)

            self.task_table.setCellWidget(row, 6, btn_widget)
        self.task_table.resizeColumnsToContents()

    def _start_task(self, task_id: int) -> None:
        if task_id in self.running_threads:
            self._add_log(f"任务 {task_id} 已在执行队列中")
            return

        def run() -> None:
            try:
                self.task_executor.execute_task(task_id)
            except Exception as e:
                logger.exception("执行任务失败: %s", e)

        th = threading.Thread(target=run, name=f"batch-task-{task_id}", daemon=True)
        th.start()
        self.running_threads[task_id] = th
        self._add_log(f"已开始执行任务 ID={task_id}")
        self._load_tasks()

    def _cancel_task(self, task_id: int) -> None:
        try:
            self.task_executor.cancel_task(task_id)
            self._add_log(f"已请求停止任务 ID={task_id}")
        except Exception as e:
            logger.error("停止任务失败: %s", e)
        self._load_tasks()

    def _on_progress_updated(self, event: BatchTaskProgressEvent) -> None:
        total = event.total or 0
        if total > 0:
            self.progress_bar.setValue(min(100, int(event.current / total * 100)))
            self.progress_bar.setVisible(True)
        self._add_log(
            f"任务 {event.task_id}: {event.current}/{event.total} "
            f"（完成 {event.completed}，失败 {event.failed}）"
        )
        self._load_tasks()

    def _on_task_completed(self, task_id: int, completed: int, failed: int) -> None:
        self._add_log(f"任务结束 ID={task_id}，完成 {completed}，失败 {failed}")
        self.running_threads.pop(int(task_id), None)
        self.progress_bar.setVisible(False)
        self._load_tasks()

    def _on_task_failed(self, task_id: int, error_message: str) -> None:
        self._add_log(f"任务失败 ID={task_id}: {error_message}")
        self.running_threads.pop(int(task_id), None)
        self.progress_bar.setVisible(False)
        self._load_tasks()

    def _add_log(self, message: str) -> None:
        from datetime import datetime

        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{ts}] {message}")

    def _show_task_detail(self, task_id: int) -> None:
        try:
            TaskDetailDialog(task_id, self.batch_task_manager, self.window() or self).exec()
        except Exception as e:
            logger.exception("打开任务详情失败: %s", e)
