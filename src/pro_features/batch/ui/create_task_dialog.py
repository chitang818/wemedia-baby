"""
批量任务创建对话框
文件路径：src/pro_features/batch/ui/create_task_dialog.py
功能：选择账号、平台、视频文件并创建 BatchTaskManagerAsync 任务（异步 API + qasync）。
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from qasync import asyncSlot

try:
    from qfluentwidgets import ComboBox, LineEdit, PrimaryPushButton, PushButton, TextEdit

    FLUENT_WIDGETS_AVAILABLE = True
except ImportError:
    FLUENT_WIDGETS_AVAILABLE = False
    ComboBox = QComboBox
    LineEdit = QLineEdit
    TextEdit = QTextEdit
    PushButton = QPushButton
    PrimaryPushButton = QPushButton

from src.ui.utils.fluent_dialogs import show_warning
from src.ui.components.base_dialog import install_escape_reject_shortcut, resolve_top_level_window_parent
from src.ui.dialogs.file_select_dialog import (
    get_last_video_import_directory,
    save_last_video_import_directory_from_path,
)

logger = logging.getLogger(__name__)


class CreateBatchTaskDialog(QDialog):
    """创建批量发布任务（视频列表 + 脚本配置 JSON）。"""

    def __init__(
        self,
        user_id: int,
        account_manager: Any,
        batch_task_manager: Any,
        parent=None,
    ):
        super().__init__(resolve_top_level_window_parent(parent))
        install_escape_reject_shortcut(self)
        self.user_id = user_id
        self.account_manager = account_manager
        self.batch_task_manager = batch_task_manager
        self.video_files: List[str] = []
        self.task_id: Optional[int] = None

        self.setWindowTitle("创建批量任务")
        self.setMinimumWidth(520)
        self.resize(720, 640)
        self._setup_ui()
        self._load_accounts_timer = QTimer(self)
        self._load_accounts_timer.setSingleShot(True)
        self._load_accounts_timer.timeout.connect(self._load_accounts_async)
        self._load_accounts_timer.start(0)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(QLabel("任务名称", self))
        self.name_edit = LineEdit(self) if FLUENT_WIDGETS_AVAILABLE else QLineEdit(self)
        self.name_edit.setPlaceholderText("请输入任务名称")
        layout.addWidget(self.name_edit)

        layout.addWidget(QLabel("发布账号", self))
        self.account_combo = ComboBox(self) if FLUENT_WIDGETS_AVAILABLE else QComboBox(self)
        layout.addWidget(self.account_combo)

        layout.addWidget(QLabel("发布平台", self))
        self.platform_combo = ComboBox(self) if FLUENT_WIDGETS_AVAILABLE else QComboBox(self)
        self.platform_combo.addItems(["douyin", "kuaishou", "wechat_video", "xiaohongshu"])
        layout.addWidget(self.platform_combo)

        row_files = QHBoxLayout()
        btn_add_file = PushButton("添加视频文件", self) if FLUENT_WIDGETS_AVAILABLE else QPushButton("添加视频文件", self)
        btn_add_folder = PushButton("添加文件夹", self) if FLUENT_WIDGETS_AVAILABLE else QPushButton("添加文件夹", self)
        btn_add_file.clicked.connect(self._add_files)
        btn_add_folder.clicked.connect(self._add_folder)
        row_files.addWidget(btn_add_file)
        row_files.addWidget(btn_add_folder)
        row_files.addStretch()
        layout.addLayout(row_files)

        self.file_list = QListWidget(self)
        self.file_list.setMinimumHeight(160)
        layout.addWidget(self.file_list)

        layout.addWidget(QLabel("标题模板（可用 {index}）", self))
        self.title_edit = LineEdit(self) if FLUENT_WIDGETS_AVAILABLE else QLineEdit(self)
        layout.addWidget(self.title_edit)

        layout.addWidget(QLabel("描述模板（可用 {index}）", self))
        self.desc_edit = TextEdit(self) if FLUENT_WIDGETS_AVAILABLE else QTextEdit(self)
        self.desc_edit.setMaximumHeight(100)
        layout.addWidget(self.desc_edit)

        retry_row = QHBoxLayout()
        retry_row.addWidget(QLabel("失败重试次数", self))
        self.retry_spin = QLineEdit(self)
        self.retry_spin.setText("3")
        retry_row.addWidget(self.retry_spin)
        retry_row.addStretch()
        layout.addLayout(retry_row)

        delay_row = QHBoxLayout()
        delay_row.addWidget(QLabel("任务间隔（秒）", self))
        self.delay_spin = QLineEdit(self)
        self.delay_spin.setText("5")
        delay_row.addWidget(self.delay_spin)
        delay_row.addStretch()
        layout.addLayout(delay_row)

        self.random_delay_check = QCheckBox("条目间随机延迟（简化策略）", self)
        self.random_delay_check.setChecked(True)
        layout.addWidget(self.random_delay_check)

        conc_row = QHBoxLayout()
        conc_row.addWidget(QLabel("最大并发（当前执行器按序执行，预留）", self))
        self.concurrent_spin = QLineEdit(self)
        self.concurrent_spin.setText("1")
        conc_row.addWidget(self.concurrent_spin)
        conc_row.addStretch()
        layout.addLayout(conc_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = PushButton("取消", self) if FLUENT_WIDGETS_AVAILABLE else QPushButton("取消", self)
        btn_create = PrimaryPushButton("创建任务", self) if FLUENT_WIDGETS_AVAILABLE else QPushButton("创建任务", self)
        btn_cancel.clicked.connect(self.reject)
        btn_create.clicked.connect(self._create_task_async)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_create)
        layout.addLayout(btn_row)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    @asyncSlot()
    async def _load_accounts_async(self) -> None:
        self.account_combo.clear()
        try:
            if not self.account_manager:
                return
            accounts = await self.account_manager.get_accounts()
        except Exception as e:
            logger.exception("加载账号列表失败: %s", e)
            return
        if not accounts:
            return
        for acc in accounts:
            name = (acc.get("platform_username") or acc.get("account_name") or "").strip() or "未命名"
            plat = (acc.get("platform") or "").strip()
            text = f"{name} ({plat})" if plat else name
            try:
                self.account_combo.addItem(text, userData=acc)
            except TypeError:
                self.account_combo.addItem(text, acc)

    def _add_files(self) -> None:
        start = get_last_video_import_directory()
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择视频文件",
            start,
            "视频 (*.mp4 *.avi *.mov *.mkv *.wmv *.m4v);;所有文件 (*.*)",
        )
        if files:
            save_last_video_import_directory_from_path(files[0])
            for f in files:
                if f not in self.video_files:
                    self.video_files.append(f)
            self._refresh_file_list()

    def _add_folder(self) -> None:
        start = get_last_video_import_directory()
        folder = QFileDialog.getExistingDirectory(self, "选择包含视频的文件夹", start)
        if not folder:
            return
        save_last_video_import_directory_from_path(folder)
        exts = (".mp4", ".avi", ".mov", ".flv", ".mkv", ".wmv", ".m4v")
        for root, _dirs, files in os.walk(folder):
            for file in files:
                if file.lower().endswith(exts):
                    path = os.path.join(root, file)
                    if path not in self.video_files:
                        self.video_files.append(path)
        self._refresh_file_list()

    def _refresh_file_list(self) -> None:
        self.file_list.clear()
        for path in self.video_files:
            item = QListWidgetItem(os.path.basename(path))
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.file_list.addItem(item)

    @asyncSlot()
    async def _create_task_async(self) -> None:
        task_name = self.name_edit.text().strip()
        if not task_name:
            show_warning(self, "提示", "请填写任务名称。")
            return
        if not self.video_files:
            show_warning(self, "提示", "请至少添加一个视频文件。")
            return
        idx = self.account_combo.currentIndex()
        if idx < 0:
            show_warning(self, "提示", "请选择发布账号。")
            return
        account = self.account_combo.itemData(idx)
        if not account:
            show_warning(self, "提示", "账号数据无效，请重新打开对话框。")
            return

        platform_username = (
            str(account.get("platform_username") or account.get("account_name") or "").strip()
        )
        if not platform_username:
            show_warning(self, "提示", "所选账号缺少平台用户名。")
            return

        platform = self.platform_combo.currentText().strip()
        title_tpl = self.title_edit.text().strip()
        desc_tpl = self.desc_edit.toPlainText().strip()

        try:
            retry_count = int(self.retry_spin.text() or "3")
        except ValueError:
            retry_count = 3
        try:
            delay_seconds = int(self.delay_spin.text() or "5")
        except ValueError:
            delay_seconds = 5
        try:
            max_concurrent = int(self.concurrent_spin.text() or "1")
        except ValueError:
            max_concurrent = 1

        videos: List[Dict[str, Any]] = []
        for i, file_path in enumerate(self.video_files, start=1):
            videos.append(
                {
                    "file_path": file_path,
                    "title": title_tpl.replace("{index}", str(i)) if title_tpl else None,
                    "description": desc_tpl.replace("{index}", str(i)) if desc_tpl else None,
                    "tags": [],
                }
            )

        script_config: Dict[str, Any] = {
            "videos": videos,
            "enable_random_delay": self.random_delay_check.isChecked(),
        }

        try:
            tid = await self.batch_task_manager.create_task(
                task_name=task_name,
                account_name=platform_username,
                platform=platform,
                task_type="video",
                script_config=script_config,
                video_count=len(self.video_files),
                retry_count=retry_count,
                delay_seconds=delay_seconds,
                max_concurrent=max_concurrent,
            )
            self.task_id = int(tid)
            logger.info("批量任务创建成功: id=%s", self.task_id)
            self.accept()
        except Exception as e:
            logger.exception("创建批量任务失败: %s", e)
            show_warning(self, "创建失败", str(e))

    def get_task_id(self) -> Optional[int]:
        return self.task_id
